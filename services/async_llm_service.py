import logging
import ssl
import aiohttp
import asyncio
from typing import Optional, Dict, Any

import certifi
from core.models.llm_model import ChatRequest


class LLMRequestError(Exception):
    """LLM請求錯誤的自定義異常。"""
    pass


class AsyncLLMService:
    """
    用於與LLM API伺服器互動的非同步服務。
    提供發送聊天請求、獲取結果和管理系統狀態的方法。
    """

    def __init__(self, base_url: str, api_key: str = None, timeout: int = 15):
        """
        使用基礎URL和可選的API金鑰初始化LLM服務。

        參數:
            base_url: LLM伺服器根URL，例如 https://sugarllmserver.zeabur.app
            api_key: 可選的認證令牌
            timeout: 請求超時時間（秒）（預設：15）
        """
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout
        self.logger = logging.getLogger("async_llm_service")

        # 建立使用 certifi CA bundle 的 SSLContext
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        connector = aiohttp.TCPConnector(ssl=ssl_ctx)

        # 設置請求標頭
        self.headers = {"Content-Type": "application/json"}
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"

        # 用相同的 SSL connector 初始化 ClientSession
        self._session = aiohttp.ClientSession(headers=self.headers, connector=connector)

        # 初始化用於存儲上一次 Pydantic 模型的屬性（如果需要）
        self._last_pydantic_model = None

        self.logger.info(f"AsyncLLMService 已初始化，基礎 URL: {base_url}，timeout: {timeout}s")

    def _build_url(self, path: str) -> str:
        """
        從基礎URL和路徑構建完整URL。

        參數:
            path: API端點路徑

        返回:
            完整URL
        """
        return f"{self.base_url}{path}"

    async def _get_session(self) -> aiohttp.ClientSession:
        """
        獲取或創建共享的 aiohttp session

        返回:
            aiohttp.ClientSession 實例
        """
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=self.headers)
        return self._session

    async def close(self):
        """
        關閉 aiohttp session
        """
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def send_chat_request(self, chat_request: ChatRequest) -> Optional[Dict[str, Any]]:
        """
        向LLM服務器發送聊天完成請求。

        參數:
            chat_request:
                model: Optional[str]
                messages: List[Message]
                temperature: Optional[float] = 0.7
                max_tokens: Optional[int] = 1000
                top_p: Optional[float] = 0.95
                response_format: Optional[str]

        返回:
            如果成功，則返回包含request_id、queue_position和estimated_time的字典
            如果請求失敗，則返回None
        """
        endpoint = self._build_url("/v1/chat/completions")

        # 建構完整的請求負載，僅包含OpenAI API支援的參數
        payload = {
            "messages": [m.model_dump() for m in chat_request.messages],  # 複製消息以避免修改原始數據
            "temperature": chat_request.temperature,
            "max_tokens": chat_request.max_tokens,
            "top_p": chat_request.top_p,
            "response_format": chat_request.response_format
        }

        if chat_request.model:
            payload["model"] = chat_request.model
            self.logger.info(f"正在向模型發送聊天請求: {chat_request.model}")
        else:
            self.logger.info("使用預設模型發送聊天請求")

        try:

            session = await self._get_session()
            async with session.post(endpoint, json=payload, timeout=self.timeout) as response:
                response.raise_for_status()
                result = await response.json()
                self.logger.info(f"聊天請求已成功發送。請求ID: {result.get('request_id')}")
                return result
        except aiohttp.ClientError as e:
            self.logger.error(f"發送聊天請求時出錯: {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"準備聊天請求時發生未預期錯誤: {str(e)}")
            return None

    async def get_chat_result(self, request_id: str) -> Optional[Dict[str, Any]]:
        """
        檢查聊天請求是否已完成。

        參數:
            request_id: 要檢查的請求ID

        返回:
            如果完成，則返回包含響應的字典
            如果尚未完成，則返回包含status: pending的字典
            如果請求失敗，則返回None
        """
        endpoint = self._build_url(f"/v1/requests/{request_id}")

        try:
            self.logger.info(f"檢查請求狀態: {request_id}")
            session = await self._get_session()
            async with session.get(endpoint, timeout=self.timeout) as response:
                response.raise_for_status()
                result = await response.json()

                if result.get("status") == "completed":
                    self.logger.info(f"請求 {request_id} 已完成")
                else:
                    self.logger.info(f"請求 {request_id} 狀態: {result.get('status')}")

                return result
        except aiohttp.ClientError as e:
            self.logger.error(f"檢查請求狀態時出錯: {str(e)}")
            return None

    async def wait_for_completion(self,
                                  request_id: str,
                                  max_wait_time: int = 60,
                                  check_interval: float = 1) -> Optional[Dict[str, Any]]:
        """
        等待聊天請求完成並獲取結果。

        參數:
            request_id: 要等待的請求ID
            max_wait_time: 最大等待時間（秒）
            check_interval: 檢查間隔（秒）

        返回:
            完成的回應字典，或在超時或錯誤情況下返回None
        """
        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < max_wait_time:
            result = await self.get_chat_result(request_id)

            if not result:
                return None

            if result.get("status") == "completed":
                return result

            if result.get("status") == "error":
                self.logger.error(f"請求 {request_id} 出錯: {result.get('message')}")
                return result

            await asyncio.sleep(check_interval)

        self.logger.warning(f"請求 {request_id} 等待超時")
        return {"status": "timeout", "message": "等待請求完成超時"}

    async def get_api_stats(self, provider: str = None) -> Optional[Dict[str, Any]]:
        """
        獲取LLM使用統計資料。

        參數:
            provider: 可選的提供者名稱，用於過濾統計資料

        返回:
            包含統計資料的字典（total_requests、tokens、cost等）
            如果請求失敗，則返回None
        """
        endpoint = self._build_url("/v1/stats")
        params = {}

        if provider:
            params["provider"] = provider

        try:
            self.logger.info("正在獲取API統計資料" + (f"，提供者: {provider}" if provider else ""))
            session = await self._get_session()
            async with session.get(endpoint, params=params, timeout=self.timeout) as response:
                response.raise_for_status()
                result = await response.json()
                self.logger.info("API統計資料已成功獲取")
                return result
        except aiohttp.ClientError as e:
            self.logger.error(f"獲取API統計資料時出錯: {str(e)}")
            return None

    async def get_system_status(self, provider: str = None) -> Optional[Dict[str, Any]]:
        """
        獲取系統和故障轉移狀態。

        參數:
            provider: 可選的提供者名稱，用於過濾狀態

        返回:
            包含系統狀態、隊列長度、指標等的字典
            如果請求失敗，則返回None
        """
        endpoint = self._build_url("/v1/system/status")
        params = {}

        if provider:
            params["provider"] = provider

        try:
            self.logger.info("正在獲取系統狀態")
            session = await self._get_session()
            async with session.get(endpoint, params=params, timeout=self.timeout) as response:
                response.raise_for_status()
                result = await response.json()
                self.logger.info("系統狀態已成功獲取")
                return result
        except aiohttp.ClientError as e:
            self.logger.error(f"獲取系統狀態時出錯: {str(e)}")
            return None

    async def get_providers(self) -> Optional[Dict[str, Any]]:
        """
        獲取所有可用的提供者。

        返回:
            包含提供者名稱、當前和主要提供者的字典
            如果請求失敗，則返回None
        """
        endpoint = self._build_url("/v1/providers")

        try:
            self.logger.info("正在獲取可用的提供者")
            session = await self._get_session()
            async with session.get(endpoint, timeout=self.timeout) as response:
                response.raise_for_status()
                result = await response.json()
                self.logger.info(f"已獲取 {len(result.get('providers', []))} 個提供者")
                return result
        except aiohttp.ClientError as e:
            self.logger.error(f"獲取提供者時出錯: {str(e)}")
            return None

    async def force_failover(self, provider: str) -> bool:
        """
        強制故障轉移到特定提供者。

        參數:
            provider: 要故障轉移到的提供者名稱

        返回:
            如果成功則返回True，否則返回False
        """
        endpoint = self._build_url(f"/v1/system/force-failover/{provider}")

        try:
            self.logger.info(f"強制故障轉移到提供者: {provider}")
            session = await self._get_session()
            async with session.post(endpoint, timeout=self.timeout) as response:
                response.raise_for_status()
                self.logger.info(f"故障轉移到 {provider} 成功")
                return True
        except aiohttp.ClientError as e:
            self.logger.error(f"強制故障轉移到 {provider} 時出錯: {str(e)}")
            return False

    async def reset_provider(self, provider: str) -> bool:
        """
        重置提供者狀態。

        參數:
            provider: 要重置的提供者名稱

        返回:
            如果成功則返回True，否則返回False
        """
        endpoint = self._build_url(f"/v1/system/reset-provider/{provider}")

        try:
            self.logger.info(f"正在重置提供者: {provider}")
            session = await self._get_session()
            async with session.post(endpoint, timeout=self.timeout) as response:
                response.raise_for_status()
                self.logger.info(f"重置提供者 {provider} 成功")
                return True
        except aiohttp.ClientError as e:
            self.logger.error(f"重置提供者 {provider} 時出錯: {str(e)}")
            return False

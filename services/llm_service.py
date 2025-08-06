import logging
import requests
from typing import Optional


class LLMRequestError(Exception):
    """LLM請求錯誤的自定義異常。"""
    pass


class LLMService:
    """
    用於與LLM API伺服器互動的服務。
    提供發送聊天請求、獲取結果和管理系統狀態的方法。
    """

    def __init__(self, base_url: str, api_key: str = None, timeout: int = 15):
        """
        使用基礎URL和可選的API金鑰初始化LLM服務。

        參數:
            base_url: LLM伺服器根URL，例如 http://localhost:8080
            api_key: 可選的認證令牌
            timeout: 請求超時時間（秒）（預設：15）
        """
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout
        self.logger = logging.getLogger("llm_service")

        # 設置請求標頭
        self.headers = {"Content-Type": "application/json"}

        # 如果提供了API金鑰，則添加Authorization標頭
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"

        self.logger.info(f"LLMService已初始化，基礎URL: {base_url}")

    def _build_url(self, path: str) -> str:
        """
        從基礎URL和路徑構建完整URL。

        參數:
            path: API端點路徑

        返回:
            完整URL
        """
        return f"{self.base_url}{path}"

    def send_chat_request(self, messages: list, model: Optional[str] = None) -> Optional[dict]:
        """
        向LLM服務器發送聊天完成請求。

        參數:
            messages: 消息對象列表，格式為 [{"role": "user", "content": "Hello"}, ...]
            model: 可選的LLM模型名稱

        返回:
            如果成功，則返回包含request_id、queue_position和estimated_time的字典
            如果請求失敗，則返回None
        """
        endpoint = self._build_url("/v1/chat/completions")
        payload = {"messages": messages}

        if model:
            payload["model"] = model
            self.logger.info(f"正在向模型發送聊天請求: {model}")
        else:
            self.logger.info("使用預設模型發送聊天請求")

        try:
            response = requests.post(endpoint, headers=self.headers, json=payload, timeout=self.timeout)
            response.raise_for_status()
            result = response.json()
            self.logger.info(f"聊天請求已成功發送。請求ID: {result.get('request_id')}")
            return result
        except requests.exceptions.RequestException as e:
            self.logger.error(f"發送聊天請求時出錯: {str(e)}")
            return None

    def get_chat_result(self, request_id: str) -> Optional[dict]:
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
            response = requests.get(endpoint, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            result = response.json()

            if result.get("status") == "completed":
                self.logger.info(f"請求 {request_id} 已完成")
            else:
                self.logger.info(f"請求 {request_id} 狀態: {result.get('status')}")

            return result
        except requests.exceptions.RequestException as e:
            self.logger.error(f"檢查請求狀態時出錯: {str(e)}")
            return None

    def get_api_stats(self, provider: str = None) -> Optional[dict]:
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
            response = requests.get(endpoint, headers=self.headers, params=params, timeout=self.timeout)
            response.raise_for_status()
            result = response.json()
            self.logger.info("API統計資料已成功獲取")
            return result
        except requests.exceptions.RequestException as e:
            self.logger.error(f"獲取API統計資料時出錯: {str(e)}")
            return None

    def get_system_status(self, provider: str = None) -> Optional[dict]:
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
            response = requests.get(endpoint, headers=self.headers, params=params, timeout=self.timeout)
            response.raise_for_status()
            result = response.json()
            self.logger.info("系統狀態已成功獲取")
            return result
        except requests.exceptions.RequestException as e:
            self.logger.error(f"獲取系統狀態時出錯: {str(e)}")
            return None

    def get_providers(self) -> Optional[dict]:
        """
        獲取所有可用的提供者。

        返回:
            包含提供者名稱、當前和主要提供者的字典
            如果請求失敗，則返回None
        """
        endpoint = self._build_url("/v1/providers")

        try:
            self.logger.info("正在獲取可用的提供者")
            response = requests.get(endpoint, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            result = response.json()
            self.logger.info(f"已獲取 {len(result.get('providers', []))} 個提供者")
            return result
        except requests.exceptions.RequestException as e:
            self.logger.error(f"獲取提供者時出錯: {str(e)}")
            return None

    def force_failover(self, provider: str) -> bool:
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
            response = requests.post(endpoint, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            self.logger.info(f"故障轉移到 {provider} 成功")
            return True
        except requests.exceptions.RequestException as e:
            self.logger.error(f"強制故障轉移到 {provider} 時出錯: {str(e)}")
            return False

    def reset_provider(self, provider: str) -> bool:
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
            response = requests.post(endpoint, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            self.logger.info(f"重置提供者 {provider} 成功")
            return True
        except requests.exceptions.RequestException as e:
            self.logger.error(f"重置提供者 {provider} 時出錯: {str(e)}")
            return False

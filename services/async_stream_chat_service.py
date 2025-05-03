# services/async_stream_chat_service.py
import logging
import asyncio
from typing import Dict, Any, List
from functools import partial
from stream_chat import StreamChat


class AsyncStreamChatService:
    """Stream Chat 服務的異步版本，提供與 Stream Chat API 交互的功能"""

    def __init__(self, api_key: str = None, api_secret: str = None):
        """初始化 Stream Chat 服務"""
        self.logger = logging.getLogger("async_stream_chat_service")
        self.api_key = api_key
        self.api_secret = api_secret
        self.client = None
        self.initialized = False

    async def initialize(self) -> bool:
        """初始化 Stream Chat 客戶端"""
        try:
            if self.initialized:
                return True

            if not self.api_key or not self.api_secret:
                self.logger.error("缺少 API 金鑰或密鑰")
                return False

            # 使用 run_in_executor 非同步執行同步的初始化代碼
            loop = asyncio.get_event_loop()
            self.client = await loop.run_in_executor(
                None, lambda: StreamChat(api_key=self.api_key, api_secret=self.api_secret))
            self.initialized = True
            self.logger.info("Async Stream Chat 服務初始化成功")
            return True
        except Exception as e:
            self.logger.error(f"Async Stream Chat 初始化失敗: {e}")
            return False

    # 查詢聊天歷史記錄
    async def get_channel_messages(self,
                                   channel_id: str,
                                   limit: int = 50,
                                   exclude_latest: bool = True) -> List[Dict[str, Any]]:
        """
        獲取頻道歷史消息
            Args:
            channel_id (str): 頻道的唯一 ID。
            limit (int): 要獲取的訊息數量上限，預設為 50。
            exclude_latest (bool): 是否排除最新一則訊息（預設為 True）。
                - 設為 True 時，會從結果中移除列表中的最後一則訊息，通常用於避免與當前輸入的內容重複。

            Returns:
                List[Dict[str, Any]]: 包含訊息字典的列表，每筆訊息結構詳見回傳格式說明。
        """
        if not self.initialized:
            await self.initialize()

        try:
            self.logger.info(f"嘗試獲取頻道 {channel_id} 的消息")

            # 創建頻道對象
            channel = self.client.channel("messaging", channel_id)

            # 如果排除最新訊息，就要增加限制數量
            query_limit = limit
            if exclude_latest and limit > 1:
                query_limit += 1
                self.logger.debug(f"排除最新訊息，增加限制數量為 {query_limit}")

            # 使用 run_in_executor 非同步執行同步的查詢代碼
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, partial(channel.query, messages={"limit": query_limit}))

            # 直接從響應中提取 messages 字段
            messages = response.get("messages", [])
            # 預設移出最新那條訊息，因為我們要分離最新訊息和歷史消息
            if exclude_latest and messages:
                messages.pop()  # 移除最後一個元素

            return messages
        except Exception as e:
            self.logger.error(f"獲取頻道消息失敗: {e}")
            return []

    # 建立或更新 AI 角色
    async def upsert_ai_user(self, user_id: str, user_name: str, user_image: str = None) -> Dict[str, Any]:
        """創建或更新 AI 用戶"""
        if not self.initialized:
            await self.initialize()

        try:
            user_data = {
                "id": user_id,
                "name": user_name,
            }

            if user_image:
                user_data["image"] = user_image

            # 使用 run_in_executor 非同步執行同步的用戶更新代碼
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: self.client.upsert_user(user_data))

            self.logger.info(f"已創建/更新 AI 用戶: {user_id}")
            return {"status": "success", "user": response}
        except Exception as e:
            self.logger.error(f"創建/更新 AI 用戶失敗: {e}")
            return {"status": "error", "reason": str(e)}

    # 發送消息
    async def send_message(self,
                           channel_id: str,
                           user_id: str,
                           sender_id: str,
                           text: str,
                           data: Dict[str, Any] = None) -> Dict[str, Any]:
        """發送消息到 Stream Chat

        Args:
            channel_id: 頻道 ID
            sender_id: 發送消息的用戶 ID
            text: 消息內容
            data: 附加數據（可選）

        Returns:
            包含操作狀態的字典
        """
        if not self.initialized:
            await self.initialize()

        try:
            # 獲取頻道
            channel = self.client.channel("messaging", channel_id)

            # 構建消息對象
            message = {"text": text}
            if data:
                message.update(data)

            # 使用 run_in_executor 非同步執行同步的發送消息代碼
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None,
                                                  lambda: channel.send_message(message=message, user_id=sender_id))
            await self.send_event(channel_id=channel_id, event={"type": "typing.stop"}, user_id=user_id)

            self.logger.info(f"發送消息到頻道 {channel_id} 成功")
            return {"status": "success", "message": response.get("message", {})}

        except Exception as e:
            self.logger.error(f"發送消息到 Stream Chat 失敗: {str(e)}")
            return {"status": "error", "reason": str(e)}

    # 創建頻道
    async def create_channel(self, channel_id: str, members: List[str], data: Dict[str, Any] = None) -> Dict[str, Any]:
        """創建新頻道

        Args:
            channel_id: 頻道 ID
            members: 頻道成員 ID 列表
            data: 頻道附加數據（可選）

        Returns:
            包含操作狀態的字典
        """
        if not self.initialized:
            await self.initialize()

        try:
            # 構建頻道數據
            channel_data = {"members": members}
            if data:
                channel_data.update(data)

            # 獲取頻道對象
            channel = self.client.channel("messaging", channel_id)

            # 使用 run_in_executor 非同步執行同步的創建頻道代碼
            creator_id = members[0] if members else "system"
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: channel.create(creator_id, channel_data))

            self.logger.info(f"創建頻道 {channel_id} 成功")
            return {"status": "success", "channel": response}
        except Exception as e:
            self.logger.error(f"創建頻道失敗: {e}")
            return {"status": "error", "reason": str(e)}

    # 創建用戶令牌
    async def create_token(self, user_id: str) -> str:
        """為指定用戶創建 JWT 令牌

        Args:
            user_id: 用戶 ID

        Returns:
            JWT 令牌字符串
        """
        if not self.initialized:
            await self.initialize()

        try:
            # 使用 run_in_executor 非同步執行同步的令牌創建代碼
            loop = asyncio.get_event_loop()
            token = await loop.run_in_executor(None, lambda: self.client.create_token(user_id))
            return token
        except Exception as e:
            self.logger.error(f"創建用戶令牌失敗: {e}")
            raise

        # 發送事件（例如 typing.start / typing.stop）
    async def send_event(self, channel_id: str, event: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """發送事件到指定頻道（例如 typing.start / typing.stop）

        Args:
            channel_id: 頻道 ID
            event: 事件資料，例如 {"type": "typing.start"}
            user_id: 觸發事件的使用者 ID（例如 AI bot 的 ID）

        Returns:
            包含操作狀態的字典
        """
        if not self.initialized:
            await self.initialize()

        try:
            channel = self.client.channel("messaging", channel_id)

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: channel.send_event(event=event, user_id=user_id))

            self.logger.info(f"已發送事件 {event.get('type')} 至頻道 {channel_id}")
            return {"status": "success", "event": response}
        except Exception as e:
            self.logger.error(f"發送事件失敗: {e}")
            return {"status": "error", "reason": str(e)}

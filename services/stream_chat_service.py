# services/stream_chat_service.py
import logging
from typing import Dict, Any, List
from stream_chat import StreamChat


class StreamChatService:
    """Stream Chat 服務，提供與 Stream Chat API 交互的功能"""

    def __init__(self, api_key: str = None, api_secret: str = None):
        """初始化 Stream Chat 服務"""
        self.logger = logging.getLogger("stream_chat_service")
        self.api_key = api_key
        self.api_secret = api_secret
        self.client = None
        self.initialized = False

    def initialize(self) -> bool:
        """初始化 Stream Chat 客戶端"""
        try:
            if self.initialized:
                return True

            if not self.api_key or not self.api_secret:
                self.logger.error("缺少 API 金鑰或密鑰")
                return False

            self.client = StreamChat(api_key=self.api_key, api_secret=self.api_secret)
            self.initialized = True
            self.logger.info("Stream Chat 服務初始化成功")
            return True
        except Exception as e:
            self.logger.error(f"Stream Chat 初始化失敗: {e}")
            return False

    # 查詢聊天歷史記錄
    def get_channel_messages(self,
                             channel_id: str,
                             limit: int = 50,
                             exclude_latest: bool = True) -> List[Dict[str, Any]]:
        """
        獲取頻道歷史消息
            Args:
            channel_id (str): 頻道的唯一 ID。
            limit (int): 要獲取的訊息數量上限，預設為 50。
            exclude_latest (bool): 是否排除最新一則訊息（預設為 False）。
                - 設為 True 時，會從結果中移除列表中的最後一則訊息，通常用於避免與當前輸入的內容重複。

            Returns:
                List[Dict[str, Any]]: 包含訊息字典的列表，每筆訊息結構詳見回傳格式說明。
        回覆格式
            {
                "id": "消息ID字串",
                "text": "消息文本內容",
                "html": "帶有HTML格式的消息文本",
                "type": "消息類型，通常是 'regular'",
                "user": {
                    "id": "發送者用戶ID",
                    "name": "發送者名稱",
                    "image": "發送者頭像URL",
                    "role": "用戶角色",
                },
                "attachments": [], // 附件數組
                "latest_reactions": [], // 最新反應
                "own_reactions": [], // 自己的反應
                "reaction_counts": {}, // 反應計數
                "reaction_scores": {}, // 反應分數
                "reply_count": 0, // 回覆數量
                "cid": "頻道ID",
                "created_at": "創建時間ISO格式",
                "updated_at": "更新時間ISO格式",
                "mentioned_users": [], // 提及的用戶
                "silent": false, // 是否靜默消息
                "pinned": false, // 是否已釘選
                "chatMode": "故事" // 自定義欄位，表示聊天模式
            }

        """
        if not self.initialized:
            self.initialize()

        try:
            self.logger.info(f"嘗試獲取頻道 {channel_id} 的消息")

            # 創建頻道對象
            channel = self.client.channel("messaging", channel_id)

            # 如果你排除最新訊息，就要在+1
            if exclude_latest and limit > 1:
                limit += 1
                self.logger.debug(f"排除最新訊息，增加限制數量為 {limit}")

            # 查詢頻道
            response = channel.query(messages={"limit": limit})

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
    def upsert_ai_user(self, user_id: str, user_name: str, user_image: str = None) -> Dict[str, Any]:
        """創建或更新 AI 用戶"""
        if not self.initialized:
            self.initialize()

        try:
            user_data = {
                "id": user_id,
                "name": user_name,
            }

            if user_image:
                user_data["image"] = user_image

            response = self.client.upsert_user(user_data)
            self.logger.info(f"已創建/更新 AI 用戶: {user_id}")
            return {"status": "success", "user": response}
        except Exception as e:
            self.logger.error(f"創建/更新 AI 用戶失敗: {e}")
            return {"status": "error", "reason": str(e)}

    # 發送消息
    def send_message(self, channel_id: str, sender_id: str, text: str, data: Dict[str, Any] = None) -> Dict[str, Any]:
        """發送消息到 Stream Chat

        Args:
            api_key: Stream Chat API 金鑰
            api_secret: Stream Chat API 密鑰
            channel_id: 頻道 ID
            user_id: 發送消息的用戶 ID
            text: 消息內容

        Returns:
            包含操作狀態的字典
        """

        if not self.initialized:
            self.initialize()

        try:
            # 獲取頻道並發送消息
            channel = self.client.channel("messaging", channel_id)

            response = channel.send_message(message={"text": text}, user_id=sender_id)

            self.logger.info(f"發送消息到頻道 {channel_id} 成功")
            return {"status": "success", "message": response.get("message", {})}

        except Exception as e:
            self.logger.error(f"發送消息到 Stream Chat 失敗: {str(e)}")
            return {"status": "error", "reason": str(e)}

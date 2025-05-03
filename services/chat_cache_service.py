from typing import Dict, List, Any, Tuple
import logging
from cachetools import TTLCache
import traceback


class ChatCacheService:
    """管理用戶與AI角色之間的對話快取服務，帶有過期時間"""

    # 快取容量和過期時間常量
    MAX_CACHE_SIZE = 1000  # 用戶-頻道組合的最大數量
    MAX_MESSAGES = 30  # 每個頻道的最大訊息數
    TTL_SECONDS = 21600  # 快取過期時間（6小時 = 6*60*60 = 21600秒）
    PROCESSED_REQUEST_TTL = 300  # 5分鐘內不重複處理同一 request_id

    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        # 使用複合鍵 (user_id, channel_id) 作為快取鍵
        # 格式: {(user_id, channel_id): {"chat_history": [...], "current_message": "..."}}
        self.message_cache = TTLCache(maxsize=self.MAX_CACHE_SIZE, ttl=self.TTL_SECONDS)
        self.user_channel_data_cache = TTLCache(maxsize=self.MAX_CACHE_SIZE, ttl=self.TTL_SECONDS)
        self._processed_messages = TTLCache(maxsize=5000, ttl=self.PROCESSED_REQUEST_TTL)
        self.character_cache = TTLCache(maxsize=50, ttl=86400)  # 角色快取，過期時間24小時
        self.logger.info("ChatCacheService 初始化完成")

    def initialize(self) -> bool:
        """初始化服務（符合 AutoServiceRegistry 的介面）"""
        try:
            self.logger.info(f"ChatCacheService 初始化成功，快取過期時間：{self.TTL_SECONDS / 3600}小時")
            return True
        except Exception as e:
            self.logger.error(f"ChatCacheService 初始化失敗: {e}")
            return False

    def _get_cache_key(self, user_id: str, channel_id: str) -> Tuple[str, str]:
        """生成快取鍵"""
        return (user_id, channel_id)

    def _ensure_cache_exists(self, user_id: str, channel_id: str) -> Dict[str, Any]:
        """
        確保指定用戶和頻道的快取存在，如果不存在則創建。
        同時更新最後訪問時間。

        Args:
            user_id (str): 使用者 ID
            channel_id (str): 頻道 ID

        Returns:
            Dict[str, Any]: 快取內容
        """
        try:
            key = self._get_cache_key(user_id, channel_id)
            if key not in self.message_cache:
                # 創建新的快取項
                self.message_cache[key] = {"chat_history": [], "current_message": ""}
                self.logger.debug(f"已為用戶 {user_id} 的頻道 {channel_id} 創建快取")
            # TTLCache 自動處理訪問更新，不需要手動更新時間戳

            return self.message_cache[key]
        except Exception as e:
            self.logger.error(f"確保快取存在時發生錯誤: {e}")
            self.logger.error(traceback.format_exc())
            # 創建一個空的快取項以確保操作可以繼續
            empty_cache = {"chat_history": [], "current_message": ""}
            self.message_cache[self._get_cache_key(user_id, channel_id)] = empty_cache
            return empty_cache

    def has_messages_history_cache(self, user_id: str, channel_id: str) -> bool:
        """
        檢查指定用戶和頻道是否已有快取
        
        Args:
            user_id (str): 使用者 ID
            channel_id (str): 頻道 ID
            
        Returns:
            bool: 是否已有快取
        """
        try:
            key = self._get_cache_key(user_id, channel_id)
            return key in self.message_cache
        except Exception as e:
            self.logger.error(f"檢查快取是否存在時發生錯誤: {e}")
            self.logger.error(traceback.format_exc())
            return False

    def get_message_cache(self, user_id: str, channel_id: str) -> Dict[str, Any]:
        """
        獲取指定用戶和頻道的對話歷史。
        如果快取不存在，返回空的快取字典。
        
        Args:
            user_id (str): 使用者 ID
            channel_id (str): 頻道 ID
            
        Returns:
            Dict[str, Any]: 包含 chat_history 和 current_message 的字典
        """
        self._ensure_cache_exists(user_id, channel_id)
        try:
            key = self._get_cache_key(user_id, channel_id)
            if key in self.message_cache:
                return self.message_cache[key]
            return {"chat_history": [], "current_message": ""}
        except Exception as e:
            self.logger.error(f"獲取對話歷史時發生錯誤: {e}")
            self.logger.error(traceback.format_exc())
            return {"chat_history": [], "current_message": ""}

    def add_message(self, user_id: str, channel_id: str, role: str, content: str) -> None:
        """
        添加新消息到快取（最新消息在列表尾部）
        
        Args:
            user_id (str): 使用者 ID
            channel_id (str): 頻道 ID
            role (str): 消息角色 ("user" 或 "assistant")
            content (str): 消息內容
        """
        try:
            # 確保快取存在
            cache = self._ensure_cache_exists(user_id, channel_id)

            # 添加新消息
            cache["chat_history"].append({"role": role, "content": content})
            self.logger.debug(f"已添加消息到快取 user:{user_id}, channel:{channel_id},內容為：{content}"
                              f"當前消息數: {len(cache['chat_history'])}")

            # 確保消息數量不超過限制（保留最新的消息）
            if len(cache["chat_history"]) > self.MAX_MESSAGES:
                cache["chat_history"] = cache["chat_history"][-self.MAX_MESSAGES:]

            self.logger.debug(f"已添加消息到快取 user:{user_id}, channel:{channel_id}, "
                              f"當前消息數: {len(cache['chat_history'])}")
        except Exception as e:
            self.logger.error(f"添加消息時發生錯誤: {e}")
            self.logger.error(traceback.format_exc())

    def store_chat_history(self, user_id: str, channel_id: str, messages: List[Dict[str, str]]) -> None:
        """
        存儲完整的對話歷史
        
        Args:
            user_id (str): 使用者 ID
            channel_id (str): 頻道 ID
            messages (List[Dict[str, str]]): 消息列表
        """
        try:
            # 確保快取存在
            cache = self._ensure_cache_exists(user_id, channel_id)

            # 存儲消息，保留最新的消息
            cache["chat_history"] = messages[-self.MAX_MESSAGES:] if len(messages) > self.MAX_MESSAGES else messages

            self.logger.info(f"已存儲{len(messages)}條消息到快取 user:{user_id}, channel:{channel_id}")
        except Exception as e:
            self.logger.error(f"存儲對話歷史時發生錯誤: {e}")
            self.logger.error(traceback.format_exc())

    def set_current_message(self, user_id: str, channel_id: str, current_message: str) -> None:
        """
        設置當前輸入
        
        Args:
            user_id (str): 使用者 ID
            channel_id (str): 頻道 ID
            current_message (str): 當前輸入的消息
        """
        try:
            # 確保快取存在
            cache = self._ensure_cache_exists(user_id, channel_id)

            # 設置當前消息
            cache["current_message"] = current_message

            self.logger.debug(f"已設置當前輸入 user:{user_id}, channel:{channel_id}")
        except Exception as e:
            self.logger.error(f"設置當前消息時發生錯誤: {e}")
            self.logger.error(traceback.format_exc())

    def clear_cache(self, user_id: str, channel_id: str) -> None:
        """
        清除指定用戶和頻道的快取
        
        Args:
            user_id (str): 使用者 ID
            channel_id (str): 頻道 ID
        """
        try:
            key = self._get_cache_key(user_id, channel_id)
            if key in self.message_cache:
                del self.message_cache[key]
                self.logger.info(f"已清除快取 user:{user_id}, channel:{channel_id}")
        except Exception as e:
            self.logger.error(f"清除快取時發生錯誤: {e}")
            self.logger.error(traceback.format_exc())

    async def convert_stream_messages_to_cache_format(self, messages: List[Dict]) -> List[Dict[str, str]]:
        """
        將Stream Chat消息轉換為快取格式

        參數:
            messages: 從 get_channel_messages 獲取的消息列表

        返回:
            轉換後的消息列表，格式為 [{"role": "user|assistant", "content": "消息內容"}, ...] 
        """
        try:
            cache_messages = []

            # 消息列表是從新到舊排列的，需要反向處理以確保時間順序正確
            for msg in messages:
                # 檢查消息是否有效
                if not isinstance(msg, dict) or 'text' not in msg or not msg['text']:
                    continue

                # 獲取用戶ID和消息內容
                user_id = msg.get("user", {}).get("id", "")
                text = msg.get("text", "")

                # 判斷是否為AI消息 - 只檢查user_id是否以"ai-"開頭
                is_ai = isinstance(user_id, str) and user_id.startswith("ai-")
                role = "assistant" if is_ai else "user"

                # 添加到結果
                if text:  # 只添加有內容的消息
                    cache_messages.append({"role": role, "content": text})

            return cache_messages
        except Exception as e:
            self.logger.error(f"轉換消息格式時發生錯誤: {e}")
            self.logger.error(traceback.format_exc())
            return []

    def has_processed_message(self, user_id: str, channel_id: str, message_id: str) -> bool:
        """
        檢查是否已處理過指定訊息
        
        Args:
            user_id (str): 使用者 ID
            channel_id (str): 頻道 ID
            message_id (str): 訊息 ID
            
        Returns:
            bool: 是否已處理過
        """
        try:
            key = f"{user_id}:{channel_id}:{message_id}"
            return key in self._processed_messages
        except Exception as e:
            self.logger.error(f"檢查訊息處理狀態時發生錯誤: {e}")
            self.logger.error(traceback.format_exc())
            return False

    def mark_message_as_processed(self, user_id: str, channel_id: str, message_id: str) -> None:
        """
        標記訊息為已處理
        
        Args:
            user_id (str): 使用者 ID
            channel_id (str): 頻道 ID
            message_id (str): 訊息 ID
        """
        try:
            key = f"{user_id}:{channel_id}:{message_id}"
            self._processed_messages[key] = True
            self.logger.debug(f"已標記訊息 {message_id} 為已處理")
        except Exception as e:
            self.logger.error(f"標記訊息為已處理時發生錯誤: {e}")
            self.logger.error(traceback.format_exc())

    def store_character(self,
                        character_id: str,
                        system_prompt: str = None,
                        levels: Dict[str, Dict[str, Any]] = None) -> None:
        """
        存儲角色資訊到快取
        
        Args:
            character_id (str): 角色 ID
            system_prompt (str, optional): 系統提示詞
            levels (Dict[str, Dict[str, Any]], optional): 等級資訊
        """
        try:
            if character_id not in self.character_cache:
                self.character_cache[character_id] = {}

            if system_prompt is not None:
                self.character_cache[character_id]["system_prompt"] = system_prompt

            if levels is not None:
                self.character_cache[character_id]["levels"] = levels

            self.logger.info(f"已存儲角色 {character_id} 的資訊到快取")
        except Exception as e:
            self.logger.error(f"存儲角色資訊時發生錯誤: {e}")
            self.logger.error(traceback.format_exc())

    def get_character_level_info(self, character_id: str, level: str) -> Dict[str, Any]:
        """
        獲取指定角色特定等級的資訊

        Args:
            character_id (str): 角色 ID
            level (str): 等級 ID

        Returns:
            Dict[str, Any]: 等級資訊
        """
        try:
            character = self.get_character(character_id)
            levels = character.get("levels", {})
            return levels.get(level, {})
        except Exception as e:
            self.logger.error(f"獲取角色等級資訊時發生錯誤: {e}")
            self.logger.error(traceback.format_exc())
            return {}

    def get_character(self, character_id: str) -> Dict[str, Any]:
        """
        獲取指定角色的完整資訊
        
        Args:
            character_id (str): 角色 ID
            
        Returns:
            Dict[str, Any]: 角色資訊
        """
        try:
            return self.character_cache.get(character_id, {})
        except Exception as e:
            self.logger.error(f"獲取角色資訊時發生錯誤: {e}")
            self.logger.error(traceback.format_exc())
            return {}

    def get_character_system_prompt(self, character_id: str) -> str:
        """
        獲取指定角色的system prompt
        
        Args:
            character_id (str): 角色 ID
            
        Returns:
            str: 系統提示詞
        """
        try:
            character = self.get_character(character_id)
            return character.get("system_prompt", "")
        except Exception as e:
            self.logger.error(f"獲取角色系統提示詞時發生錯誤: {e}")
            self.logger.error(traceback.format_exc())
            return ""

    def has_character_cache(self, character_id: str) -> bool:
        """
        檢查是否有指定角色的快取
        
        Args:
            character_id (str): 角色 ID
            
        Returns:
            bool: 是否有該角色的快取
        """
        try:
            return character_id in self.character_cache
        except Exception as e:
            self.logger.error(f"檢查角色快取時發生錯誤: {e}")
            self.logger.error(traceback.format_exc())
            return False

    def _ensure_channel_data_cache_exists(self, user_id: str, channel_id: str) -> Dict[str, Any]:
        """
        確保指定用戶和頻道的數據快取存在，如果不存在則創建默認結構。

        Args:
            user_id (str): 使用者 ID
            channel_id (str): 頻道 ID

        Returns:
            Dict[str, Any]: 快取內容
        """
        try:
            key = self._get_cache_key(user_id, channel_id)
            if key not in self.user_channel_data_cache:
                # 創建新的快取項，使用默認值初始化
                default_data = {
                    "user_persona": {},
                    "meta_data": {
                        "intimacy": 0,
                        "total_intimacy": 0,
                        "intimacy_percentage": 0,
                        "current_level": "",
                        "next_level": "",
                        "lock_level": 1,
                    }
                }
                self.user_channel_data_cache[key] = default_data
                self.logger.debug(f"已為用戶 {user_id} 的頻道 {channel_id} 創建頻道數據快取")

            return self.user_channel_data_cache[key]
        except Exception as e:
            self.logger.error(f"確保頻道數據快取存在時發生錯誤: {e}")
            self.logger.error(traceback.format_exc())
            # 創建一個空的快取項以確保操作可以繼續
            default_data = {
                "user_persona": {},
                "meta_data": {
                    "intimacy": 0,
                    "total_intimacy": 0,
                    "intimacy_percentage": 0,
                    "current_level": "",
                    "next_level": "",
                    "lock_level": 1,
                }
            }
            self.user_channel_data_cache[self._get_cache_key(user_id, channel_id)] = default_data
            return default_data

    def has_channel_data_cache(self, user_id: str, channel_id: str) -> bool:
        """
        檢查指定用戶和頻道是否已有數據快取
        
        Args:
            user_id (str): 使用者 ID
            channel_id (str): 頻道 ID
            
        Returns:
            bool: 是否已有快取
        """
        try:
            key = self._get_cache_key(user_id, channel_id)
            return key in self.user_channel_data_cache
        except Exception as e:
            self.logger.error(f"檢查頻道數據快取是否存在時發生錯誤: {e}")
            self.logger.error(traceback.format_exc())
            return False

    def get_channel_data(self, user_id: str, channel_id: str) -> Dict[str, Any]:
        """
        獲取指定用戶和頻道的數據。
        如果快取不存在，返回默認數據結構。
        
        Args:
            user_id (str): 使用者 ID
            channel_id (str): 頻道 ID
            
        Returns:
            Dict[str, Any]: 包含 user_persona 和 meta_data 的字典
        """
        return self._ensure_channel_data_cache_exists(user_id, channel_id)

    def convert_firebase_to_channel_data(self, firebase_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        將Firebase返回的數據轉換為快取格式
        
        Args:
            firebase_data (Dict[str, Any]): Firebase返回的原始數據
            
        Returns:
            Dict[str, Any]: 轉換後的快取格式數據
        """
        try:
            # 預設數據結構
            channel_data = {
                "user_persona": {},
                "meta_data": {
                    "intimacy": 0,
                    "total_intimacy": 0,
                    "intimacy_percentage": 0,
                    "current_level": "",
                    "next_level": "",
                    "lock_level": 1,
                }
            }

            # 從Firebase數據中提取user_persona
            if "user_persona" in firebase_data:
                channel_data["user_persona"] = firebase_data["user_persona"]

            # 從Firebase數據中提取meta_data
            if "meta_data" in firebase_data:
                meta_data = firebase_data["meta_data"]
                # 提取各個字段，如果不存在則使用默認值
                channel_data["meta_data"]["intimacy"] = meta_data.get("intimacy", 0)
                channel_data["meta_data"]["total_intimacy"] = meta_data.get("total_intimacy", 0)
                channel_data["meta_data"]["intimacy_percentage"] = meta_data.get("intimacy_percentage", 0)
                channel_data["meta_data"]["current_level"] = meta_data.get("current_level", "")
                channel_data["meta_data"]["next_level"] = meta_data.get("next_level", "")
                channel_data["meta_data"]["lock_level"] = meta_data.get("lock_level", 1)

            self.logger.debug("已將Firebase數據轉換為頻道數據快取格式")
            return channel_data
        except Exception as e:
            self.logger.error(f"轉換Firebase數據時發生錯誤: {e}")
            self.logger.error(traceback.format_exc())
            # 返回默認結構
            return {
                "user_persona": {},
                "meta_data": {
                    "intimacy": 0,
                    "total_intimacy": 0,
                    "intimacy_percentage": 0,
                    "current_level": "",
                    "next_level": "",
                    "lock_level": 1,
                }
            }

    def store_channel_data(self, user_id: str, channel_id: str, channel_data: Dict[str, Any]) -> None:
        """
        存儲用戶頻道數據到快取
        
        Args:
            user_id (str): 使用者 ID
            channel_id (str): 頻道 ID
            channel_data (Dict[str, Any]): 頻道數據
        """
        try:
            key = self._get_cache_key(user_id, channel_id)
            self.user_channel_data_cache[key] = channel_data
            self.logger.info(f"已存儲用戶 {user_id} 在頻道 {channel_id} 的數據到快取")
        except Exception as e:
            self.logger.error(f"存儲頻道數據時發生錯誤: {e}")
            self.logger.error(traceback.format_exc())

    def update_channel_data_field(self, user_id: str, channel_id: str, field_path: str, value: Any) -> Dict[str, Any]:
        """
        更新頻道數據中的特定字段
        
        Args:
            user_id (str): 使用者 ID
            channel_id (str): 頻道 ID
            field_path (str): 字段路徑，例如 "meta_data.intimacy" 或 "user_persona.traits.kindness"
            value (Any): 新值
            
        Returns:
            Dict[str, Any]: 更新後的完整頻道數據
        """
        try:
            # 確保快取存在
            data = self._ensure_channel_data_cache_exists(user_id, channel_id)

            # 解析字段路徑
            parts = field_path.split('.')
            target = data

            # 遍歷路徑，直到最後一個部分之前
            for i, part in enumerate(parts[:-1]):
                if part not in target:
                    target[part] = {}
                target = target[part]

            # 設置最後一部分的值
            target[parts[-1]] = value

            self.logger.debug(f"已更新用戶 {user_id} 在頻道 {channel_id} 的數據字段 {field_path}")
            return data
        except Exception as e:
            self.logger.error(f"更新頻道數據字段時發生錯誤: {e}")
            self.logger.error(traceback.format_exc())
            return self._ensure_channel_data_cache_exists(user_id, channel_id)

    def clear_channel_data_cache(self, user_id: str, channel_id: str) -> None:
        """
        清除指定用戶和頻道的數據快取
        
        Args:
            user_id (str): 使用者 ID
            channel_id (str): 頻道 ID
        """
        try:
            key = self._get_cache_key(user_id, channel_id)
            if key in self.user_channel_data_cache:
                del self.user_channel_data_cache[key]
                self.logger.info(f"已清除用戶 {user_id} 在頻道 {channel_id} 的數據快取")
        except Exception as e:
            self.logger.error(f"清除頻道數據快取時發生錯誤: {e}")
            self.logger.error(traceback.format_exc())

import logging
from typing import Any, Dict
from services.async_firebase_service import AsyncFirebaseService
from services.chat_cache_service import ChatCacheService
from services.async_stream_chat_service import AsyncStreamChatService


class FetchCacheService:
    """
    負責通用的 fetch + cache 流程管理。
    """
    MAX_MESSAGES = 20

    def __init__(self, firebase_service: AsyncFirebaseService, chat_cache_service: ChatCacheService,
                 stream_chat_service: AsyncStreamChatService, logger: logging.Logger):
        self.firebase_service = firebase_service
        self.chat_cache_service = chat_cache_service
        self.stream_chat_service = stream_chat_service
        self.logger = logger

    async def fetch_and_cache_character(self, character_id: str, request_locale: str = None) -> Dict[str, Any]:
        """
        通用的 fetch + cache（針對角色資料）。

        raw_data 格式預期：
        {
            'main_doc': {...},
            'system_prompt': {...},   # 子集合 info 分析結果
            'levels': [...],          # 子集合 info 分析結果
        }

        回傳結構範例：
        {
          'system_prompt': {...},     # dict
          'levels': { '1': {...}, ... }
        }
        """
        self.logger.info(f"Fetching character {character_id} with requested locale {request_locale}")
        # 1. 快取命中檢查
        if self.chat_cache_service.has_character_cache(character_id):
            return self.chat_cache_service.get_character(character_id)

        # 2. 呼叫 fetch_cache 一次拉所有子集合
        raw_data = await self.firebase_service.query_document(
            collection="Characters",
            doc_id=character_id,)

        if not raw_data:
            self.logger.warning(f"_fetch_character 未取得角色 {character_id} 原始資料")
            return {}

        i18n = raw_data.get('i18n', {})
        if not i18n:
            self.logger.warning(f"Character {character_id}'s i18n is empty")
            return {}

        if "default_locale" not in raw_data:
            logging.warning(f"Character {character_id}'s default_locale not found")
        locale = raw_data.get("default_locale", None)
        if request_locale and request_locale in i18n.keys():
            locale = request_locale

        self.logger.info(f"Fetching character {character_id} with requested locale {request_locale}, use {locale}")
        if locale is None:
            self.logger.warning(f"Character {character_id}'s locale is None")
            return {}

        # 3. 解析 system_prompt 和 levels
        system_prompt: Dict[str, Any] = i18n.get(locale, {}).get('system_prompt', {}) or {}
        levels_raw = i18n.get(locale, {}).get('levels', {}) or {}
        levels = sorted(levels_raw, key=lambda level: level['intimacy'])

        # systemPrompt 直接使用返回的字典
        if not isinstance(system_prompt, dict):
            self.logger.warning(f"角色 {character_id} systemPrompt 子集合格式不符，預期字典: {type(system_prompt)}")
            system_prompt = {}

        # 從 levels 字典中提取 info 陣列
        # 4. 將 levels list 轉成字典格式
        levels_map: Dict[str, Any] = {str(i + 1): lvl for i, lvl in enumerate(levels)}

        # 5. 寫入 chat cache
        self.chat_cache_service.store_character(character_id=character_id,
                                                system_prompt=system_prompt,
                                                levels=levels_map)

        # 6. 回傳完整快取內容
        cached_data = self.chat_cache_service.get_character(character_id)
        self.logger.debug(f"角色 {character_id} 快取內容: {cached_data}")
        if cached_data is None:  # 增加檢查以避免返回 None
            self.logger.error(f"無法從快取獲取剛存儲的角色數據: {character_id}")
            return {}  # 返回空字典而不是 None

        return cached_data

    async def fetch_and_cache_messages(self, user_id: str, channel_id: str, current_message: str,
                                       role: str) -> Dict[str, Any]:
        """
        通用的 fetch + cache（針對聊天歷史）。
        """
        # self.chat_cache_service.set_current_message(user_id, channel_id, current_message)
        # 1. 快取命中檢查
        if self.chat_cache_service.has_messages_history_cache(user_id, channel_id):
            # 如果 role 是 character，則只需要 add message
            if role == "assistant":
                self.chat_cache_service.add_message(user_id, channel_id, role, current_message)
            elif role == "user":
                # self.chat_cache_service.add_message(user_id, channel_id, role, current_message)
                self.chat_cache_service.set_current_message(user_id, channel_id, current_message)
            return self.chat_cache_service.get_message_cache(user_id, channel_id)
        else:
            messages_history = await self.stream_chat_service.get_channel_messages(channel_id=channel_id,
                                                                                   limit=self.MAX_MESSAGES)
            self.logger.debug(f"Channel 查詢回應: {messages_history}")
            converted_messages = await self.chat_cache_service.convert_stream_messages_to_cache_format(messages_history)
            self.logger.debug(f"擷取出的 messages: {converted_messages}")
            # 順便存放 meta_data 與 user_persona

            # 寫入 chat cache
            self.chat_cache_service.store_chat_history(user_id, channel_id, converted_messages)
            # 如果 role 是 character，則只需要 add message
            if role == "user":
                self.chat_cache_service.set_current_message(user_id, channel_id, current_message)
        """
        預計 message_cache是
        user_id{
            channel_id:{
                chat_history:[],
                current_message:""
            },
            channel_id:{
                chat_history:[],
                current_message:""
            },

        },
        user_id{
            channel_id:{
                chat_history:[],
                current_message:""
            },
            channel_id:{
                chat_history:[],
                current_message:""
            },

        }
        """

        # 回傳快取內容
        return self.chat_cache_service.get_message_cache(user_id, channel_id)

    async def store_and_cache_user_channel_data(self, user_id: str, channel_id: str,
                                                channel_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        建立 channel 時，把 user_persona 與 meta_data 快取，
        並把完整 channel_data 寫入 Firestore。

        Returns:
            已快取的 channel_data_cache
        """
        # 欄位預檢
        persona = channel_data.get("user_persona")
        meta = channel_data.get("meta_data") or {}
        required_meta_keys = [
            "intimacy", "total_intimacy", "intimacy_percentage", "current_level", "next_level", "lock_level"
        ]
        missing = [k for k in required_meta_keys if k not in meta]
        if persona is None or missing:
            raise ValueError(f"channel_data 欄位不足，缺少: user_persona={persona is None}, meta_data keys={missing}")

        # 組成要快取的 payload
        channel_data_cache = {"user_persona": persona, "meta_data": {k: meta[k] for k in required_meta_keys}}

        # 1) 快取
        try:
            self.chat_cache_service.store_channel_data(user_id, channel_id, channel_data_cache)
        except Exception as e:
            self.logger.error(f"[store_cache] user={user_id} channel={channel_id} 失敗: {e}")
            raise

        # 2) 寫入 Firestore
        try:
            await self.firebase_service.set_document("channels", channel_id, channel_data)
        except Exception as e:
            self.logger.error(f"[firestore] set_document user={user_id} channel={channel_id} 失敗: {e}")
            raise

        return channel_data_cache

    async def fetch_and_cache_channel_data(self,channel_id: str) -> dict[str, Any] | None:
        """
        先從快取拿 channel_data，沒有時再從 Firestore 拉取、轉換、快取並回傳。
        回傳 None 表示該 channel 尚未建立或不存在。
        """

        # 1. 快取命中
        cached = self.chat_cache_service.has_channel_data_cache( channel_id)
        if cached:
            self.logger.debug(f"快取命中，從快取拿 channel_data: channel={channel_id}")
            cached = self.chat_cache_service.get_channel_data(channel_id)
            return cached

        self.logger.debug(f"快取未命中，從 Firestore 拉取 channel_data:  channel={channel_id}")

        # 2. 從 Firestore 拉
        try:
            raw = await self.firebase_service.get_document("channels", channel_id)
        except Exception as e:
            self.logger.error(f"讀取 Firestore channels/{channel_id} 失敗：{e}")
            raise

        if not raw:
            self.logger.warning(f"channels/{channel_id} 文件不存在")
            return None

        # 3. 轉換並驗證
        try:
            channel_data = self.chat_cache_service.convert_firebase_to_channel_data(raw)
        except Exception as e:
            self.logger.error(f"轉換 Firestore 資料失敗：{e}, raw={raw}")
            raise

        # 4. 寫入快取
        try:
            self.chat_cache_service.store_channel_data(channel_id, channel_data)
        except Exception as e:
            self.logger.error(f"快取 channel_data 失敗：{e}")

        # 5. 回傳
        return channel_data

    async def update_and_cache_channel_data(self, channel_id: str, new_data: Dict[str, Any]) -> None:
        """
        更新 channel_data（可能是 user_persona、meta_data 或兩者），並同步更新 cache 與 Firestore。

        new_data 例:
        {"user_persona": {...}}
        或 {"meta_data": {...}}
        或同時更新兩者：
        {"user_persona": {...}, "meta_data": {...}}
        """
        # 1. 先從 cache 拿現有資料（若沒有就空 dict）
        existing = self.chat_cache_service.get_channel_data(channel_id) or {}

        # 2. 合併 new_data 到 existing
        merged = {**existing, **new_data}

        # 3. 更新快取
        #    chat_cache_service 期望存的是只有 user_persona & meta_data
        self.chat_cache_service.store_channel_data(channel_id, merged)

        # 4. 讀 Firestore 原始文件（可能有更多欄位）
        try:
            raw = await self.firebase_service.get_document("channels", channel_id) or {}
        except Exception as e:
            self.logger.error(f"[firestore] get_document {channel_id} 失敗: {e}")
            raise

        # 5. 把 new_data 合併回 raw，確保不丟失其他欄位
        raw.update(new_data)

        # 6. 寫回 Firestore
        try:
            await self.firebase_service.set_document("channels", channel_id, raw)
        except Exception as e:
            self.logger.error(f"[firestore] set_document {channel_id} 失敗: {e}")
            raise

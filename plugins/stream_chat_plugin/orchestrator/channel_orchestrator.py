import logging
from typing import Any, Dict
import traceback

from core.models.user_persona_model import UserPersona
from services.async_firebase_service import AsyncFirebaseService
from services.chat_cache_service import ChatCacheService
from services.async_stream_chat_service import AsyncStreamChatService
from ..utils import FetchCacheService
from ..utils import get_current_level_title, get_next_level_title


class ChannelOrchestrator:

    def __init__(
        self,
        firebase_service: AsyncFirebaseService,
        chat_cache_service: ChatCacheService,
        stream_chat_service: AsyncStreamChatService,
    ):
        self.firebase_service = firebase_service
        self.chat_cache_service = chat_cache_service
        self.stream_chat_service = stream_chat_service
        self.logger = logging.getLogger(__name__)
        self.fetch_cache_service = FetchCacheService(self.firebase_service, self.chat_cache_service,
                                                     self.stream_chat_service, self.logger)

    async def create_channel(self, channel_id: str, user_id: str, character_id: str) -> dict:
        """
        建立頻道，抓取角色與使用者資料，產生初始回應
        """
        try:
            self.logger.debug(f"開始建立頻道: channel_id={channel_id}, user_id={user_id}, character_id={character_id}")

            try:
                character_info = await self.fetch_cache_service.fetch_and_cache_character(character_id, request_locale=None)
                levels = character_info.get("levels", {})
            except Exception as e:
                self.logger.error(f"抓取角色資料失敗: {str(e)}")
                self.logger.error(traceback.format_exc())
                return {"error": f"抓取角色資料失敗: {str(e)}", "status": "error"}

            # 2. 抓使用者 persona
            try:
                self.logger.debug(f"開始抓取使用者 {user_id} 的 persona")
                user_persona = await self.fetch_user_persona(user_id)
                self.logger.debug(f"使用者 persona 抓取結果: {user_persona}")
            except Exception as e:
                self.logger.error(f"抓取使用者 persona 失敗: {str(e)}")
                self.logger.error(traceback.format_exc())
                user_persona = {"name": "None", "birthDay": "None", "gender": "None", "promises": [None]}
                self.logger.info(f"使用預設 persona: {user_persona}")

            try:
                current_level = get_current_level_title(levels, 0)
                next_level = get_next_level_title(levels, 0)

                channel_doc = {
                    "channel_id": channel_id,
                    "created_at": self.firebase_service.get_server_timestamp(),
                    "user_persona": user_persona,
                    "meta_data": {
                        "intimacy": 0,
                        "total_intimacy": 0,
                        "intimacy_percentage": 0,
                        "current_level": current_level,
                        "next_level": next_level,
                        "lock_level": 1,
                    }
                }

                self.logger.debug(f"角色快取: {character_info}")
                self.logger.debug(f"使用者快取: {user_persona}")
                self.logger.info(f"channel_doc: {channel_doc}")

                await self.fetch_cache_service.store_and_cache_user_channel_data(user_id, channel_id, channel_doc)
                # await self.firebase_service.set_document("channels", channel_id, channel_doc)
                self.logger.info(f"成功建立頻道文件: {channel_id}")
            except Exception as e:
                self.logger.error(f"建立頻道文件失敗: {str(e)}")
                self.logger.error(traceback.format_exc())
                return {"error": f"建立頻道文件失敗: {str(e)}", "status": "error"}

            return {"status": "success"}

        except Exception as e:
            self.logger.error(f"建立頻道時發生未預期的錯誤: {str(e)}")
            self.logger.error(traceback.format_exc())
            return {"error": f"建立頻道時發生未預期的錯誤: {str(e)}", "first_message": "抱歉，我現在有點問題，請稍後再試。"}

    async def fetch_user_persona(self, user_id: str) -> Dict[str, Any]:
        """
        預設的 user_persona 都是 None
        """
        try:
            self.logger.debug(f"開始抓取使用者 persona: {user_id}")
            # 這裡可以擴充實際從資料庫抓取使用者資料的邏輯

            default_persona = UserPersona()
            user_persona = default_persona.model_dump()

            self.logger.debug(f"返回使用者 persona: {user_persona}")
            return user_persona

        except Exception as e:
            self.logger.error(f"抓取使用者 persona 時發生錯誤: {str(e)}")
            self.logger.error(traceback.format_exc())
            raise

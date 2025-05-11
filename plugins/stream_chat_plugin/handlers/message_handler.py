from typing import Dict, Any
import logging
from plugins.stream_chat_plugin.utils import is_ai_message, get_character_id, get_receiver_user_id

from plugins.stream_chat_plugin.utils.fetch_cache_service import FetchCacheService
from services.chat_cache_service import ChatCacheService
from services.async_firebase_service import AsyncFirebaseService
from services.async_llm_service import AsyncLLMService
from services.async_stream_chat_service import AsyncStreamChatService
from plugins.stream_chat_plugin.orchestrator.chat_orchestrator import ChatOrchestrator


class AsyncMessageHandler:
    """
    非同步處理 Stream Chat 訊息的類別，透過 ChatOrchestrator 來協調生成回應
    """

    def __init__(self,
                 llm_service: AsyncLLMService,
                 firebase_service: AsyncFirebaseService,
                 chat_cache_service: ChatCacheService,
                 stream_chat_service: AsyncStreamChatService,
                 logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.llm_service = llm_service
        self.firebase_service = firebase_service
        self.chat_cache_service = chat_cache_service
        self.stream_chat_service = stream_chat_service

        self.orchestrator = ChatOrchestrator(llm_service=self.llm_service,
                                             firebase_service=self.firebase_service,
                                             chat_cache_service=self.chat_cache_service,
                                             stream_chat_service=self.stream_chat_service,
                                             logger=self.logger)
        self.fetch_cache_service = FetchCacheService(self.firebase_service, self.chat_cache_service,
                                                     self.stream_chat_service, self.logger)

    async def handle_message(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        message = event_data.get("message", {})
        channel_id = event_data.get("channel_id") or message.get("cid")
        user = event_data.get("user", {})
        sender_id = user.get("id")
        text = message.get("text", "")
        chat_mode = message.get("chatMode", "故事")
        reply_word = message.get("responseLength", "10")
        lockedLevel = message.get("lockedLevel", "1")
        ticket_cost = message.get("cost", "0")
        members = event_data.get("members", [])

        character_id = get_character_id(members=members)
        message_id = message.get("id")
        ai_name = self.get_ai_character_name(event_data.get("members", []))
        print(f"這次的角色是：{ai_name}")

        # 防重機制
        if self.chat_cache_service.has_processed_message(sender_id, channel_id, message_id):
            self.logger.warning(f"已處理過此訊息，跳過: {message_id}")
            return {"status": "skipped", "reason": "duplicate", "message_id": message_id}
        else:
            self.chat_cache_service.mark_message_as_processed(sender_id, channel_id, message_id)

        # 如果是 AI 發送的訊息，僅記錄快取
        if is_ai_message(sender_id):
            receiver_user_id = get_receiver_user_id(members, sender_id)
            await self.fetch_cache_service.fetch_and_cache_messages(user_id=receiver_user_id,
                                                                    channel_id=channel_id,
                                                                    current_message=text,
                                                                    role="assistant")
            self.logger.info(f"跳過 AI 角色訊息，不處理: {message_id}")
            return {"status": "skipped", "reason": "AI 發送的訊息", "message_id": message_id}
        else:
            # 發出 typing.start 事件
            try:
                await self.stream_chat_service.send_event(channel_id=channel_id,
                                                          event={"type": "typing.start"},
                                                          user_id=character_id)
            except Exception as e:
                self.logger.warning(f"發送 typing.start 失敗: {e}")

            response = None
            # 產生回應
            response = await self.orchestrator.generate_response(
                user_id=sender_id,
                channel_id=channel_id,
                current_message=text,
                character_id=character_id,
                chat_mode=chat_mode,
                reply_word=reply_word,
                lockedLevel=lockedLevel,
            )

            usage = response.get("usage")
            usage["ticket_cost"] = int(ticket_cost)
            usage["character"] = ai_name
            if usage:
                # 寫入 Firestore
                await self.firebase_service.upsert_channel_message_usage(
                    channel_id=channel_id,
                    message_id=message_id,
                    usage_payload=usage,
                )
                await self.firebase_service.upsert_user_spend_logs(
                    user_id=sender_id,
                    message_id=message_id,
                    usage_payload=usage,
                )

            return {
                "status": "success",
                "character_id": character_id,
                "channel_id": channel_id,
                "response": response,
                "processed": True
            }

    def get_ai_character_name(self, members: list) -> str:
        for member in members:
            user_id = member.get("user_id", "")
            if user_id.startswith("ai-"):
                user = member.get("user", {})
                return user.get("name", "")
        return ""

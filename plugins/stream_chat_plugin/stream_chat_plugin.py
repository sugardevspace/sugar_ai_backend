# plugins/stream_chat_plugin/stream_chat_plugin.py
import logging
import time
from typing import Any, Dict

from plugins.stream_chat_plugin.orchestrator.channel_orchestrator import ChannelOrchestrator
from .handlers import AsyncMessageHandler
from services.async_firebase_service import AsyncFirebaseService
from services.async_stream_chat_service import AsyncStreamChatService
from services.async_llm_service import AsyncLLMService
from services.chat_cache_service import ChatCacheService
from plugins.plugin_base import BasePlugin
from .utils import identify_channel_members


class AsyncStreamChatPlugin(BasePlugin):

    # 提示一下 code 比較好寫
    firebase_service: AsyncFirebaseService
    stream_chat_service: AsyncStreamChatService
    llm_service: AsyncLLMService
    chat_cache_service: ChatCacheService
    message_handler: AsyncMessageHandler
    """處理 Stream Chat webhook 事件的非同步插件"""

    @property
    def plugin_name(self) -> str:
        return "async_stream_chat_plugin"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "處理 Stream Chat webhook 事件的非同步插件"

    async def init_plugin(self, services: Dict[str, Any]) -> None:
        await super().init_plugin(services)
        self.logger = logging.getLogger(self.plugin_name)

        # 取得 stream chat service
        self.stream_chat_service = services.get("stream_chat")
        if not self.stream_chat_service:
            self.logger.warning("Stream Chat 服務未找到，某些功能可能受限")

        # chat cache 服務
        self.chat_cache_service = services.get("chat_cache")
        if not self.chat_cache_service:
            self.logger.warning("Chat Cache 服務未找到，某些功能可能受限")

        # 從服務中獲取需要的依賴
        self.firebase_service = services.get("firebase")
        if not self.firebase_service:
            self.logger.warning("資料庫服務未找到，某些功能可能受限")

        self.llm_service = services.get("llm")
        if not self.llm_service:
            self.logger.warning("LLM 服務未找到，某些功能可能受限")

        # 初始化訊息處理器
        self.message_handler = AsyncMessageHandler(self.llm_service, self.firebase_service, self.chat_cache_service,
                                                   self.stream_chat_service, self.logger)

        # 初始化插件狀態
        self.stats = {"events_processed": 0, "messages_processed": 0, "last_processed": None}

        self.channel_orchestrator = ChannelOrchestrator(firebase_service=self.firebase_service,
                                                        chat_cache_service=self.chat_cache_service,
                                                        stream_chat_service=self.stream_chat_service)

    async def start(self) -> None:
        await super().start()
        self.logger.info("非同步 Stream Chat 插件已啟動")

    async def stop(self) -> None:
        self.logger.info("非同步 Stream Chat 插件已停止")
        await super().stop()

    async def handle_event(self, event_type: str, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """處理來自 Stream Chat 的各種事件"""
        self.logger.info(f"收到事件類型: {event_type}")

        # 更新基本統計信息
        self.stats["events_processed"] += 1
        self.stats["last_processed"] = time.time()

        # 根據事件類型分發到對應的處理方法
        if event_type == "message.new":
            result = await self._handle_new_message(event_data)
            return result
        elif event_type == "create_character":
            return await self._handle_create_character(event_data)
        elif event_type == "channel.created":
            result = await self._handle_channel_created(event_data)
            return result
        else:
            self.logger.warning(f"未處理的事件類型: {event_type}")
            return {"status": "ignored", "reason": f"未處理的事件類型: {event_type}"}

    async def _handle_new_message(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """處理新消息事件"""
        try:
            # 交給 MessageHandler 處理詳細邏輯
            result = await self.message_handler.handle_message(event_data)

            # 如果成功處理，更新統計信息
            if result.get("status") == "success":
                self.stats["messages_processed"] += 1
                """傳回訊息給使用者"""
                await self.stream_chat_service.send_message(result["channel_id"], result["character_id"],
                                                            result["character_id"], result["response"]["text"])

            return result

        except Exception as e:
            self.logger.exception(f"處理新消息時發生錯誤: {e}")
            return {"status": "error", "reason": str(e)}

    async def _handle_channel_created(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """處理頻道創建事件"""
        try:
            channel_id = event_data.get("channel_id")
            channel_type = event_data.get("channel_type")

            # 獲取 members 列表
            members = event_data.get("members", []) or event_data.get("channel", {}).get("members", [])

            # 檢查必要參數
            if not channel_id or not channel_type or not members:
                return {"status": "error", "reason": "缺少必要參數: channel_id, channel_type 或 members"}

            # 使用工具函數識別成員
            character_id, user_id, ai_name, user_name = identify_channel_members(members)

            self.logger.debug(f"頻道 {channel_id}: AI={character_id}, 用戶={user_id}")

            if character_id and user_id:

                result = await self.channel_orchestrator.create_channel(channel_id, user_id, character_id)

                return {
                    "status": result["status"],
                    "channel_id": channel_id,
                    "character_id": character_id,
                    "user_id": user_id,
                }

            # 其他情況
            return {"status": "success", "channel_id": channel_id, "message": f"成功創建頻道: {channel_id}"}

        except Exception as e:
            self.logger.error(f"創建頻道時發生錯誤: {e}")
            return {"status": "error", "reason": str(e)}

    async def _handle_create_character(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """處理創建 AI 角色的請求"""
        try:

            character_id = event_data.get("character_id")
            character_name = event_data.get("character_name")
            character_image = event_data.get("character_image", "")

            if not character_id or not character_name:
                return {"status": "error", "reason": "缺少必要參數: character_id 和 character_name 是必須的"}

            # 確保角色 ID 有正確前綴
            if not character_id.startswith("ai-"):
                character_id = f"ai-{character_id}"

            # 在 Stream Chat 中創建用戶
            result = await self.stream_chat_service.upsert_ai_user(
                user_id=character_id,
                user_name=character_name,
                user_image=character_image,
            )

            if result.get("status") == "success":
                self.logger.info(f"成功創建 AI 角色: {character_id}")
                return {"status": "success", "character_id": character_id, "message": f"成功創建 AI 角色: {character_name}"}
            else:
                return result

        except Exception as e:
            self.logger.error(f"創建 AI 角色時發生錯誤: {e}")
            return {"status": "error", "reason": str(e)}

    async def get_status(self) -> Dict[str, Any]:
        """獲取插件狀態"""
        status = await super().get_status()
        status.update({"stats": self.stats})
        return status

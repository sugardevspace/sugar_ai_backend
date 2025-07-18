import logging
import traceback
from typing import Dict, Any
from core.models.llm_model import ChatRequest
from plugins.stream_chat_plugin.orchestrator.chat_orchestrator import ChatOrchestrator
from plugins.stream_chat_plugin.utils.fetch_cache_service import FetchCacheService
from services.async_llm_service import AsyncLLMService
from services.async_firebase_service import AsyncFirebaseService
from services.chat_cache_service import ChatCacheService
from services.async_stream_chat_service import AsyncStreamChatService
from plugins.plugin_base import BasePlugin
from .utils import extract_ai_id


class AsyncLevelPlugin(BasePlugin):

    firebase_service: AsyncFirebaseService
    stream_chat_service: AsyncStreamChatService
    chat_cache_service: ChatCacheService
    llm_service: AsyncLLMService

    @property
    def plugin_name(self) -> str:
        return "async_level_plugin"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Plugin description"

    async def init_plugin(self, services: Dict[str, Any]) -> None:
        """初始化，會自動注入 services dict"""
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

        self.orchestrator = ChatOrchestrator(llm_service=self.llm_service,
                                             firebase_service=self.firebase_service,
                                             chat_cache_service=self.chat_cache_service,
                                             stream_chat_service=self.stream_chat_service,
                                             logger=self.logger)
        self.fetch_cache_service = FetchCacheService(self.firebase_service, self.chat_cache_service,
                                                     self.stream_chat_service, self.logger)

    async def start(self) -> None:
        """啟動插件"""
        await super().start()
        self.logger.info(f"Plugin {self.plugin_name} started")

    async def stop(self) -> None:
        """停止插件"""
        self.logger.info(f"Plugin {self.plugin_name} stopping")
        await super().stop()

    async def handle_event(self, event_type: str, event_data: Dict[str, Any]) -> Any:
        """處理傳進來的事件，回傳要放到 results 裡的 dict"""
        try:
            self.logger.info("Processing level event")
            channel_id = event_data["channel_id"]
            level = event_data["level"]
            character_id = extract_ai_id(channel_id)
            chat_mode = "level"

            # 發出 typing.start 事件
            try:
                await self.stream_chat_service.send_event(channel_id=channel_id,
                                                          event={"type": "typing.start"},
                                                          user_id=character_id)
            except Exception as e:
                self.logger.warning(f"發送 typing.start 失敗: {e}")

            character_data = await self.fetch_cache_service.fetch_and_cache_character(character_id)
            if not character_data or "levels" not in character_data:
                self.logger.error(f"角色 {character_id} 的資料或等級資訊不存在")
                return {"error": "角色資料不完整", "first_message": "抱歉，我現在有點問題，請稍後再試。"}

            level_str = str(level)  # 確保 level 是字串形式
            if level_str not in character_data["levels"]:
                self.logger.warning(f"角色 {character_id} 不存在等級 {level_str}，使用等級 1")
                level_str = "1"  # 默認使用等級 1

            level_data = character_data["levels"][level_str]
            if "scene_prompt" not in level_data:
                self.logger.warning(f"角色 {character_id} 的等級 {level_str} 中沒有 scene_prompt 資料")
                return {"error": "等級提示不存在", "first_message": "抱歉，我現在有點問題，請稍後再試。"}


            character_levels = character_data["levels"]
            current_level = character_levels.get(level_str)
            tone_style = current_level['tone_style']
            relationship = current_level['relationship']
            reply_word = "200"
            character_system_prompt = character_data.get("system_prompt", {})
            character_system_prompt_str = (
                f'{character_system_prompt["general_prompt"]}，'
                f'生成回覆字數{character_system_prompt["reply_word"][reply_word]}，'
                f'輸出格式：{character_system_prompt["output_format"]["story"]}，'
                f'生成回覆字數{character_system_prompt["reply_word"][reply_word]}，'
                f'{character_system_prompt["unique_specialty"]}，基本身份：{character_system_prompt["basic_identity"]}，'
                f'語氣風格：{tone_style}，'
                f'和使用者關係：{relationship}，'
                f'口頭禪：{character_system_prompt["mantra"]}，'
                f'喜好與厭惡：{character_system_prompt["like_dislike"]}，'
                f'家庭背景：{character_system_prompt["family_background"]}，'
                f'重要角色：{character_system_prompt["important_role"]}，'
                f'外貌：{character_system_prompt["appearance"]}')

            scene_prompt_str = level_data["scene_prompt"]

            messages = [{"role": "system", "content": character_system_prompt_str}]
            messages.append({"role": "user", "content": scene_prompt_str})

            request_response = await self.llm_service.send_chat_request(
                ChatRequest(model=None, messages=messages, response_format=chat_mode))
            response = await self.llm_service.wait_for_completion(request_response["request_id"],
                                                                  max_wait_time=180,
                                                                  check_interval=1)
            structured_output = response.get("structured_output", {})
            self.logger.info(f"LLM 回應結果: {structured_output}")

            dialogues = structured_output.get("dialogues", [])
            messages = []
            for item in dialogues:
                msg = item.get("message", "").strip()
                mood = item.get("action_mood", "").strip()
                # 空的話略過
                if msg:
                    messages.append(f"(*{mood}*){msg}" if mood else msg)

            # 3. 使用 stream_chat_service 發送訊息到頻道
            if self.stream_chat_service:
                await self.stream_chat_service.send_message(
                    channel_id=channel_id,
                    user_id=character_id,
                    sender_id=character_id,
                    text="".join(messages),
                )
                self.logger.info(f"已向頻道 {channel_id} 發送角色 {character_id} 的等級 {level_str} 提示")

                try:
                    await self.stream_chat_service.send_event(channel_id=channel_id,
                                                              event={"type": "typing.stop"},
                                                              user_id=character_id)
                except Exception as e:
                    self.logger.warning(f"發送 typing.stop 失敗: {e}")
                return {"success": True, "message": f"已發送等級 {level_str} 的提示"}
            else:
                self.logger.error("Stream Chat 服務不可用，無法發送訊息")
                return {"error": "Stream Chat 服務不可用", "first_message": "抱歉，我現在有點問題，請稍後再試。"}

        except Exception as e:
            self.logger.error(f"處理事件時發生錯誤: {str(e)}")
            self.logger.error(traceback.format_exc())
            return {"error": f"處理事件失敗: {str(e)}", "first_message": "抱歉，我現在有點問題，請稍後再試。"}

    async def _fetch_and_cache_character_levels(self, uid: str) -> None:
        """
        查詢指定 uid 的角色，抓取其 levels/info 中的整份 list，轉為 dict 存入快取
        Args:
            uid (str): 角色 ID
        """
        try:
            self.logger.debug(f"開始抓取角色等級資料: {uid}")

            results = await self.firebase_service.query_documents_with_subcollection_map(collection="ai_character",
                                                                                         filters=[("uid", "==", uid)],
                                                                                         sub_collection="levels",
                                                                                         sub_doc_id="info")

            self.logger.debug(f"查詢結果數量: {len(results)}")

            if not results:
                self.logger.warning(f"未找到角色 {uid} 的等級資料")
                return

            for entry in results:
                main_doc = entry.get("main_doc")
                if not main_doc:
                    self.logger.warning(f"查詢結果中缺少 main_doc: {entry}")
                    continue

                sub_doc_data = entry.get("sub_doc_data")  # 這是 Firestore 中 levels/info 的內容
                if sub_doc_data is None:
                    self.logger.warning(f"查詢結果中缺少 sub_doc_data: {entry}")
                    continue

                character_id = main_doc.get("uid")
                if not character_id:
                    self.logger.warning(f"main_doc 中缺少 uid: {main_doc}")
                    continue

                system_prompt = main_doc.get("system_prompt", "")

                self.logger.debug(f"sub_doc_data 類型: {type(sub_doc_data)}, 值: {sub_doc_data}")

                # 處理 sub_doc_data 各種可能的格式
                level_list = None

                # 如果 sub_doc_data 是字典，檢查是否有 'info' 鍵
                if isinstance(sub_doc_data, dict):
                    if 'info' in sub_doc_data and isinstance(sub_doc_data['info'], list):
                        # 從 {'info': [列表內容]} 中取出列表
                        level_list = sub_doc_data['info']
                        self.logger.debug(f"從 sub_doc_data['info'] 獲取列表，長度: {len(level_list)}")
                    else:
                        # 其他字典格式，直接使用
                        levels_map = sub_doc_data
                        self.logger.debug(f"使用現有字典結構: {list(levels_map.keys())[:5]}...")
                elif isinstance(sub_doc_data, list):
                    # 如果已經是列表，直接使用
                    level_list = sub_doc_data
                    self.logger.debug(f"直接使用列表，長度: {len(level_list)}")
                else:
                    self.logger.warning(f"無法識別的 sub_doc_data 類型: {type(sub_doc_data)}")
                    continue

                # 如果找到了列表，將其轉換為字典
                if level_list is not None:
                    levels_map = {str(index + 1): level_data for index, level_data in enumerate(level_list)}
                    self.logger.debug(f"轉換列表為字典: {list(levels_map.keys())}")

                # 儲存至快取
                self.chat_cache_service.store_character(character_id=character_id,
                                                        system_prompt=system_prompt,
                                                        levels=levels_map)
                self.logger.info(f"成功快取角色 {character_id} 的等級資料")
        except Exception as e:
            self.logger.error(f"抓取及快取角色等級資料時發生錯誤: {str(e)}")
            self.logger.error(traceback.format_exc())
            raise

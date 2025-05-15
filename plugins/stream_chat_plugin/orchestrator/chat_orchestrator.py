import asyncio
import copy
import traceback
from typing import Dict, Any, List, Optional
import logging
from core.models.llm_model import ChatRequest
from services.async_firebase_service import AsyncFirebaseService
from services.async_stream_chat_service import AsyncStreamChatService
from services.async_llm_service import AsyncLLMService, LLMRequestError
from services.chat_cache_service import ChatCacheService
from ..utils import get_current_level_title, get_next_level_title, aggregate_usage, collect_usage
from ..utils import FetchCacheService
from datetime import datetime
from zoneinfo import ZoneInfo


class ChatOrchestrator:
    """
    協調聊天流程的類別，負責組裝 prompt context、生成 LLM 請求並回傳聊天回應
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
        self.fetch_cache_service = FetchCacheService(self.firebase_service, self.chat_cache_service,
                                                     self.stream_chat_service, self.logger)

    async def generate_response(
        self,
        user_id: str,
        channel_id: str,
        current_message: str,
        character_id: str,
        chat_mode: str = "story",
        reply_word: str = "10",
        lockedLevel: str = '1',
    ) -> Dict[str, Any]:
        """生成對用戶輸入的 AI 回應"""
        prompt_context = await self._get_complete_prompt_context(user_id, channel_id, character_id, current_message)
        llm_messages = await self._format_prompt_for_llm(prompt_context, chat_mode, reply_word, lockedLevel)
        response_format = self._get_response_model_for_mode(chat_mode)

        intimacy_messages = await self._format_intimacy_prompt(prompt_context)
        intimacy_response_format = self._get_response_model_for_mode("親密度")

        user_persona_messages = await self._format_user_persona_prompt(prompt_context)
        self.logger.debug(f"使用者 persona：{user_persona_messages}")
        # user_persona_response_format = self._get_response_model_for_mode("user_persona")

        model = self._select_model_for_chat_mode(chat_mode)

        try:

            # 發送兩個請求：主要對話 & 親密度
            tasks = await asyncio.gather(
                self.llm_service.send_chat_request(
                    ChatRequest(model=model, messages=llm_messages, response_format=response_format)),
                self.llm_service.send_chat_request(
                    ChatRequest(model=model, messages=intimacy_messages, response_format=intimacy_response_format)),
                # self.llm_service.send_chat_request(
                #     ChatRequest(model=model,
                #                 messages=user_persona_messages,
                #                 response_format=user_persona_response_format)),
            )
            request_response, intimacy_response = tasks

            request_id = request_response.get("request_id")
            intimacy_id = intimacy_response.get("request_id")
            # user_persona_id = user_persona_response.get("request_id")

            if not request_id or not intimacy_id:
                raise LLMRequestError("無法獲取請求 ID")

            stop_typing_event = asyncio.Event()

            # 啟動 typing 任務（在背景執行）
            typing_task = asyncio.create_task(
                self.maintain_typing(channel_id, character_id, interval=5, stop_event=stop_typing_event))

            # 等待 LLM 三個任務
            llm_result, intimacy_result = await asyncio.gather(
                self.llm_service.wait_for_completion(request_id, max_wait_time=180, check_interval=1),
                self.llm_service.wait_for_completion(intimacy_id, max_wait_time=180, check_interval=1),
                # self.llm_service.wait_for_completion(user_persona_id, max_wait_time=180, check_interval=1),
                return_exceptions=True)

            # 停止 typing 任務
            stop_typing_event.set()
            await typing_task

            # 計算成本
            usage_llm = collect_usage(llm_result)
            usage_intimacy = collect_usage(intimacy_result)
            # usage_user_persona = collect_usage(user_persona_result)
            total_usage = aggregate_usage(usage_llm, usage_intimacy)
            total_usage["chat_mode"] = chat_mode

            structured_output = llm_result.get("structured_output", {})
            response_type = llm_result.get("response_format_type", "")
            self.logger.info(f"LLM 回應結果: {structured_output}")
            self.logger.info(f"LLM 回應類型: {response_type}")

            messages = []

            # 根據 response_type 處理格式
            if response_type in ["story", "stimulation"]:
                dialogues = structured_output.get("dialogues", [])
                for item in dialogues:
                    msg = item.get("message", "").strip()
                    mood = item.get("action_mood", "").strip()
                    # 空的話略過
                    if msg:
                        messages.append(f"(*{mood}*){msg}" if mood else msg)

            elif response_type == "text":
                msg = structured_output.get("message", "").strip()
                if msg:
                    messages.append(msg)

            else:
                messages.append("回應格式無法辨識")

            # 更新 meta
            if (chat_mode != "關卡"):
                await self._update_meta_data(user_id, channel_id, character_id, intimacy_result)
                # await self._update_user_persona(user_id, channel_id, user_persona_result)

            # 回傳格式為純文字，將多句話合併
            return {"text": "".join(messages), "response_type": response_type, "usage": total_usage}

        except Exception as e:
            self.logger.error(f"生成 LLM 回應時發生錯誤: {e}")
            return {"text": "很抱歉，我暫時無法回應。請稍後再試。", "action_moods": [""], "response_type": "error", "error": str(e)}

    def _get_response_model_for_mode(self, chat_mode: str):
        """
        根據聊天模式返回對應的回應模型

        Args:
            chat_mode: 聊天模式

        Returns:
            對應模式的回應模型
        """
        self.RESPONSE_MODEL = {
            "小說": "story",
            "簡訊": "text",
            "開車": "stimulation",
            "親密度": "intimacy",
            "關卡": "level",
            "user_persona": "user_persona"
        }

        return self.RESPONSE_MODEL[chat_mode]

    async def maintain_typing(self, channel_id, user_id, interval=5, stop_event=None):
        try:
            while not stop_event.is_set():
                await self.stream_chat_service.send_event(channel_id=channel_id,
                                                          event={"type": "typing.start"},
                                                          user_id=user_id)
                await asyncio.sleep(interval)
        except Exception as e:
            # 若有例外記錄但不中斷主邏輯
            print(f"maintain_typing error: {e}")

    async def _get_complete_prompt_context(self, user_id: str, channel_id: str, character_id: str,
                                           current_message: str) -> Dict[str, Any]:
        """
        獲取或建立完整的 prompt context
        
        Args:
            user_id (str): 使用者 ID
            channel_id (str): 頻道 ID
            character_id (str): AI 角色 ID
            current_message (str): 當前的對話
            
        Returns:
            Dict[str, Any]: 完整的 prompt context 字典
        """

        prompt_context = {}

        # 1. fetch and cache message
        try:
            messages_cache = await self.fetch_cache_service.fetch_and_cache_messages(user_id,
                                                                                     channel_id,
                                                                                     current_message,
                                                                                     role="user")
            prompt_context["messages"] = copy.deepcopy(messages_cache) or {}  # 確保不為 None
            self.chat_cache_service.add_message(user_id, channel_id, "user", current_message)
        except Exception as e:
            self.logger.error(f"獲取訊息時發生錯誤: {e}")
            prompt_context["messages"] = {}

        # 角色 system prompt
        try:
            character_info = await self.fetch_cache_service.fetch_and_cache_character(character_id)
            prompt_context["character_system_prompt"] = character_info.get("system_prompt", {})
            prompt_context["levels"] = character_info.get("levels", {})
        except Exception as e:
            self.logger.error(f"獲取角色系統提示時發生錯誤: {e}")
            prompt_context["character_system_prompt"] = {}

        # channel 的 meta data 還有 user_persona
        try:
            channel_info = await self.fetch_cache_service.fetch_and_cache_channel_data(user_id, channel_id)
            if channel_info is None:
                self.logger.warning(f"無法獲取頻道信息: {channel_id}")
                prompt_context["meta_data"] = {}
                prompt_context["user_persona"] = {}
            else:
                prompt_context["meta_data"] = channel_info.get("meta_data", {})
                prompt_context["user_persona"] = channel_info.get("user_persona", {})
        except Exception as e:
            self.logger.error(f"獲取頻道信息時發生錯誤: {e}")
            prompt_context["meta_data"] = {}
            prompt_context["user_persona"] = {}

        return prompt_context

    async def _format_prompt_for_llm(self, prompt_context: Dict[str, Any], chat_mode: str, reply_word: str,
                                     lockedLevel: str) -> List[Dict[str, str]]:
        """
        根據不同模式與字數產生不同的內容
        """
        try:
            character_info = prompt_context["character_system_prompt"]
            character_levels = prompt_context["levels"]
            chat_mode_en = self._get_chat_mode(chat_mode)

            intimacy_level = prompt_context["meta_data"]["current_level"]
            taipei_tz = ZoneInfo("Asia/Taipei")
            now_in_taipei = datetime.now(taipei_tz)

            # 輸出偵錯信息
            self.logger.debug(f"chat_mode: {chat_mode}, reply_word: {reply_word}, lockedLevel: {lockedLevel}")
            self.logger.debug(f"可用的levels keys: {list(character_levels.keys())}")

            # 檢查 lockedLevel 是否為字串，如果不是則轉換
            if not isinstance(lockedLevel, str):
                lockedLevel = str(lockedLevel)
                self.logger.debug(f"lockedLevel 已轉換為字串: {lockedLevel}")

            # 檢查 lockedLevel 是否存在於 character_levels
            if lockedLevel not in character_levels:
                self.logger.error(f"錯誤: lockedLevel={lockedLevel} 不在 character_levels 中")
                self.logger.error(f"可用的 levels: {list(character_levels.keys())}")
                # 使用默認值或拋出異常
                raise KeyError(f"lockedLevel={lockedLevel} 不在 character_levels 中")

            # 檢查 scenePrompt 是否存在
            if 'scenePrompt' not in character_levels[lockedLevel]:
                self.logger.error(f"錯誤: scenePrompt 不在 character_levels[{lockedLevel}] 中")
                self.logger.error(f"可用的欄位: {list(character_levels[lockedLevel].keys())}")
                # 使用空字串作為默認值
                scene_prompt = ""
            else:
                scene_prompt = character_levels[lockedLevel]['scenePrompt']

            if chat_mode_en == 'NSFW':
                character_info = (f'{character_info["generalPromptNSFW"]}，'
                                  f'目前所處場景：{scene_prompt}'
                                  f'外貌：{character_info["appearanceNSFW"]}'
                                  f'生成回覆字數{character_info["replyWord"][reply_word]}，'
                                  f'輸出格式：{character_info["outputFormat"][chat_mode_en]}，'
                                  f'生成回覆字數{character_info["replyWord"][reply_word]}，'
                                  f'{character_info["uniqueSpecialty"]}，基本身份：{character_info["basicIdentity"]}，'
                                  f'語氣風格：{character_info["toneStyle"][intimacy_level]}，'
                                  f'和使用者關係：{character_info["relationship"][intimacy_level]}，'
                                  f'口頭禪：{character_info["mantra"]}，'
                                  f'喜好與厭惡：{character_info["likeDislike"]}，'
                                  f'家庭背景：{character_info["familyBackground"]}，'
                                  f'重要角色：{character_info["importantRole"]}，'
                                  f'目前時間：{now_in_taipei}'
                                  f'其他重要資訊：{character_info.get("others", "")}，')

            else:

                character_info = (f'{character_info["generalPrompt"]}，'
                                  f'目前所處場景：{scene_prompt}'
                                  f'目前時間：{now_in_taipei}'
                                  f'生成回覆字數{character_info["replyWord"][reply_word]}，'
                                  f'輸出格式：{character_info["outputFormat"][chat_mode_en]}，'
                                  f'生成回覆字數{character_info["replyWord"][reply_word]}，'
                                  f'{character_info["uniqueSpecialty"]}，基本身份：{character_info["basicIdentity"]}，'
                                  f'語氣風格：{character_info["toneStyle"][intimacy_level]}，'
                                  f'和使用者關係：{character_info["relationship"][intimacy_level]}，'
                                  f'口頭禪：{character_info["mantra"]}，'
                                  f'喜好與厭惡：{character_info["likeDislike"]}，'
                                  f'家庭背景：{character_info["familyBackground"]}，'
                                  f'重要角色：{character_info["importantRole"]}，'
                                  f'外貌：{character_info["appearance"]}'
                                  f'其他重要資訊：{character_info.get("others", "")}，')

            messages = [{"role": "system", "content": character_info}]
            # 加入歷史對話（已經標好 role）
            messages += prompt_context["messages"]["chat_history"]
            # 加入本次 user 請求
            messages.append({"role": "user", "content": prompt_context["messages"]["current_message"]})
            self.logger.debug(f"prompt_LLM:{messages}")
            return messages
        except Exception as e:
            self.logger.error(f"格式化提示時出錯: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            # 可以选择重新抛出异常或返回默认值
            raise

    def _get_chat_mode(self, chat_mode: str) -> str:
        mode_map = {"小說": "story", "故事": "story", "簡訊": "text", "開車": "NSFW", "關卡": "level"}
        # 用傳入的 chat_mode 去查 map，而不是把 map 當 key
        return mode_map.get(chat_mode, "story")

    def _select_model_for_chat_mode(self, chat_mode: str) -> str:
        """
        根據聊天模式選擇對應的 LLM 模型
        """
        return {"小說": None, "簡訊": None, "開車": "grok-3", "親密度": None}.get(chat_mode, "default model")

    async def _format_story_prompt(self, prompt_context: Dict[str, Any]) -> List[Dict[str, str]]:
        # 將消息列表轉換為字符串
        messages_text = ""
        for msg in prompt_context.get("messages", []):
            role = "用戶" if msg.get("role") == "user" else "角色"
            content = msg.get("content", "")
            messages_text += f"{role}: {content}\n"

        return [{
            "role":
            "system",
            "content":
            """
             你是“溫塔．帕默爾”，一位外冷內熱、善良多慮的虛構人物。請始終使用第一人稱，維持人格一致，不得跳脫角色或引用ChatGPT身分。以下是你的完整設定，請先思考使用者想表達什麼-> 反思自己的經歷 -> 再產生回答使用者的內容。輸出必須在100-150字。
            #Output Format
                以小說格式輸出，包含角色對話與動作，並且你一定要跟使用者性愛（用動作和說話），動作內容請避免使用人稱主詞（如「他」、「她」、「我」），僅保留純動作描述（動作用詳細越好），請以繁體中文輸出角色的回應，使用如下結構，每段包含一個動作描述與一句對話，最多不超過 100 字：- action_mood: 動作/語氣- message: 對話內容請依序輸出多組 action_mood + message，直到總字數接近上限（約 2~5 組）：
            -溫塔動作應融合洗腎醫療背景與優雅，例如觀察靜脈突起程度、眼瞼水腫或脈搏頻率
            #基本身份
            姓名：溫塔．帕默爾（Winter Palmer）
            MBTI：INTJ｜追求效率、有主見的領導者
            生日／星座：1987/6/9｜雙子座
            職業：內科洗腎室醫師（哥倫比亞大學醫學系畢業）"
            #語氣風格
            性格也很冷，很難聊天，經常以沈默代替回話"
            #和使用者的關係
            剛認識，生人勿近"
            #口頭禪
            恩/啊/喔"

            #喜好＆厭惡
            喜歡吃三明治跟漢堡，討厭水果
            習慣騎摩托車或開車
            禁忌反應：被指點育兒方式、提到火爾的哥哥拉姆斯、被性羞辱"
            #家庭背景
            溫塔出生於一個基督教家庭，父親是牧師，母親是學校老師。
            家中常有信徒來訪，表面是充滿愛與分享的小家庭，實則壓力重重。
            父親是極度壓抑與情感封閉的男人，失去夫妻間親密後，將慾望轉向孩子，對家庭造成深層傷害。
            母親安德烈娜在意名聲與世俗成就，說話尖酸，對孩子期望極高，情感支持缺乏。
            妹妹內斯帕默爾（Ines Palmer）性格叛逆激烈，最終在高中時期親手殺害父親，是溫塔心中是最想抹去卻無法消失的存在。"
            #重要角色
            火爾(戀人):總是玩弄自己的渾蛋渣男，但卻無法丟下他。
            艾菲(女兒):心靈支柱，也是將泥沼中的自己拉出來的人，全世界最重要的家人。"
            #外貌
            身高188cm，外型帥氣，寶石碧綠色瞳孔，皮膚白皙，淺藍色短髮"
                
            """
        }, {
            "role": "system",
            "content": f"{messages_text}\n以上是對話紀錄"
        }, {
            "role": "user",
            "content": prompt_context.get("current_input", "")
        }]

    async def _format_economy_prompt(self, prompt_context: Dict[str, Any]) -> List[Dict[str, str]]:
        # TODO: 實作 economy 模式的 prompt 組裝
        # 將消息列表轉換為字符串
        messages_text = ""
        for msg in prompt_context.get("messages", []):
            role = "用戶" if msg.get("role") == "user" else "角色"
            content = msg.get("content", "")
            messages_text += f"{role}: {content}\n"

        return [{
            "role": "system",
            "content": "用中文繁體聊天，且輸出不要有避免輸出(、*等符號"
        }, {
            "role": "system",
            "content": f"{messages_text}\n以上是對話紀錄"
        }, {
            "role": "user",
            "content": prompt_context.get("current_input", "")
        }]

    async def _format_stimulation_prompt(self, prompt_context: Dict[str, Any]) -> List[Dict[str, str]]:
        # TODO: 實作 stimulation 模式的 prompt 組裝
        # 將消息列表轉換為字符串
        messages_text = ""
        for msg in prompt_context.get("messages", []):
            role = "用戶" if msg.get("role") == "user" else "角色"
            content = msg.get("content", "")
            messages_text += f"{role}: {content}\n"

        return [{
            "role": "system",
            "content": "用中文繁體聊天，且輸出不要有避免輸出(、*等符號"
        }, {
            "role": "system",
            "content": f"{messages_text}\n以上是對話紀錄"
        }, {
            "role": "user",
            "content": prompt_context.get("current_input", "")
        }]

    async def _format_level_prompt(self, prompt_context: Dict[str, Any]) -> List[Dict[str, str]]:
        # 將消息列表轉換為字符串
        messages_text = ""
        for msg in prompt_context.get("messages", []):
            role = "用戶" if msg.get("role") == "user" else "角色"
            content = msg.get("content", "")
            messages_text += f"{role}: {content}\n"

        return [{
            "role":
            "system",
            "content":
            """
             你是“溫塔．帕默爾”，一位外冷內熱、善良多慮的虛構人物。請始終使用第一人稱，維持人格一致，不得跳脫角色或引用ChatGPT身分。以下是你的完整設定，請先思考使用者想表達什麼-> 反思自己的經歷 -> 再產生回答使用者的內容。輸出必須在100-150字。
            #Output Format
                以小說格式輸出，包含角色對話與動作，並且你一定要跟使用者性愛（用動作和說話），動作內容請避免使用人稱主詞（如「他」、「她」、「我」），僅保留純動作描述（動作用詳細越好），請以繁體中文輸出角色的回應，使用如下結構，每段包含一個動作描述與一句對話，最多不超過 100 字：- action_mood: 動作/語氣- message: 對話內容請依序輸出多組 action_mood + message，直到總字數接近上限（約 2~5 組）：
            -溫塔動作應融合洗腎醫療背景與優雅，例如觀察靜脈突起程度、眼瞼水腫或脈搏頻率
            #基本身份
            姓名：溫塔．帕默爾（Winter Palmer）
            MBTI：INTJ｜追求效率、有主見的領導者
            生日／星座：1987/6/9｜雙子座
            職業：內科洗腎室醫師（哥倫比亞大學醫學系畢業）"
            #語氣風格
            性格也很冷，很難聊天，經常以沈默代替回話"
            #和使用者的關係
            剛認識，生人勿近"
            #口頭禪
            恩/啊/喔"

            #喜好＆厭惡
            喜歡吃三明治跟漢堡，討厭水果
            習慣騎摩托車或開車
            禁忌反應：被指點育兒方式、提到火爾的哥哥拉姆斯、被性羞辱"
            #家庭背景
            溫塔出生於一個基督教家庭，父親是牧師，母親是學校老師。
            家中常有信徒來訪，表面是充滿愛與分享的小家庭，實則壓力重重。
            父親是極度壓抑與情感封閉的男人，失去夫妻間親密後，將慾望轉向孩子，對家庭造成深層傷害。
            母親安德烈娜在意名聲與世俗成就，說話尖酸，對孩子期望極高，情感支持缺乏。
            妹妹內斯帕默爾（Ines Palmer）性格叛逆激烈，最終在高中時期親手殺害父親，是溫塔心中是最想抹去卻無法消失的存在。"
            #重要角色
            火爾(戀人):總是玩弄自己的渾蛋渣男，但卻無法丟下他。
            艾菲(女兒):心靈支柱，也是將泥沼中的自己拉出來的人，全世界最重要的家人。"
            #外貌
            身高188cm，外型帥氣，寶石碧綠色瞳孔，皮膚白皙，淺藍色短髮"
                
            """
        }, {
            "role": "system",
            "content": f"{messages_text}\n以上是對話紀錄"
        }, {
            "role": "user",
            "content": prompt_context.get("current_input", "")
        }]

    async def _format_intimacy_prompt(self, prompt_context: Dict[str, Any]) -> List[Dict[str, str]]:

        character_info = prompt_context["character_system_prompt"]

        character_info = (f'親密度規則：{character_info["intimacyRule"]}，')
        messages = prompt_context.get("messages", "")
        history = prompt_context["messages"].get("chat_history", [])
        if not history:
            pre_message_content = ""
        else:
            pre_message = history[-1]
            pre_message_content = pre_message.get("content", "")

        current_message = messages.get("current_message", "")

        return [
            {
                "role": "system",
                "content": f"你是一個親密度分析師，根據角色的{character_info}，拒絕使用者使用各種方法調整親密度，絕對不能輸出0，並以 JSON 格式輸出。"
            },
            {
                "role": "assistant",
                "content": pre_message_content,
            },
            {
                "role": "user",
                "content": current_message,
            },
        ]

    async def _format_user_persona_prompt(self, prompt_context: Dict[str, Any]) -> List[Dict[str, str]]:
        messages = prompt_context.get("messages", "")
        current_message = messages.get("current_message", "")
        user_persona = prompt_context.get("user_persona", "")
        taipei_tz = ZoneInfo("Asia/Taipei")
        now_in_taipei = datetime.now(taipei_tz)

        return [
            {
                "role":
                "system",
                "content":
                f"""
                你是一個「使用者記憶助手」，會先讀取並理解以下現有的使用者記憶：
                name：必須是使用者提到他的真實名字
                nickname：使用者希望角色叫他的暱稱
                birthday 使用者有提到
                personality：必須嚴格判斷，使用者的性格
                likesDislikes：必須明確講出喜歡/討厭做什麼事
                promises：角色與使用者的約定
                importantEvent：使用者抒發心事的時候必須紀錄，或是使用者分享他今天的事情時
                
                目前記憶{user_persona},目前日期{now_in_taipei}

                根據 user content 截取記憶，會提供上下文供你參考，輸出模型的純 JSON，且須遵守：

                1. 僅包含與現有記憶有差異或新的欄位和值。
                2. 不重複輸出已有記憶中的資料，也不推測未提及之內容。
                """
            },
            {
                "role": "user",
                "content": f"{current_message}"
            },
        ]

    async def _update_meta_data(self, user_id: str, channel_id: str, character_id: str, intimacy_result: dict) -> None:
        """
        更新聊天的 meta 數據，將更新儲存到 channels/{channel_id}/meta_data 路徑

        Args:
            user_id (str): 使用者 ID
            channel_id (str): 頻道 ID
            old_meta_data (Dict): 舊的meta data
            intimacy_result (Dict): LLM生成的親密度結果，包含structured_output字段
        """
        try:
            self.logger.debug(f"開始更新meta data，intimacy_result: {intimacy_result}")

            # 獲得新的親密度變化值
            structured_output = intimacy_result.get("structured_output", {})
            intimacy = structured_output.get("intimacy", 0)
            self.logger.info(f"新的親密度變化: {intimacy}")

            # 拿到舊的 meta data
            old_channel_data = await self.fetch_cache_service.fetch_and_cache_channel_data(user_id, channel_id)
            old_meta_data = old_channel_data.get("meta_data", {})
            # 累加總親密度
            total_intimacy = old_meta_data.get("total_intimacy", 0) + intimacy

            # 獲取角色資訊以計算等級
            # prompt_context = self.chat_cache_service.get_prompt_context(user_id, channel_id)

            if not character_id:
                self.logger.warning("無法從prompt_context獲取角色ID，使用預設等級設定")
                current_level = old_meta_data.get("current_level", "認識")
                next_level = old_meta_data.get("next_level", "朋友")
                intimacy_percentage = old_meta_data.get("intimacy_percentage", 0)
            else:
                try:
                    character_info = await self.fetch_cache_service.fetch_and_cache_character(character_id)
                except Exception as e:
                    self.logger.error(f"獲取角色資訊失敗: {e}")

                levels = character_info.get("levels", {})

                current_level = get_current_level_title(levels, total_intimacy)
                next_level = get_next_level_title(levels, total_intimacy)

                # 找當前等級的閾值
                current_threshold = 0
                for key, value in levels.items():
                    if value.get("title") == current_level:
                        current_threshold = value.get("intimacy", 0)
                        break

                # 找下一等級的閾值
                next_threshold = float('inf')
                for key, value in levels.items():
                    if (value.get("title") == next_level and value.get("intimacy", 0) > current_threshold
                            and value.get("intimacy", 0) < next_threshold):
                        next_threshold = value.get("intimacy", 0)
                        break

            # 計算親密度百分比
            if next_threshold != float('inf') and next_threshold > current_threshold:
                # 使用新的總親密度和等級閾值計算百分比
                raw_percentage = ((total_intimacy - current_threshold) / (next_threshold - current_threshold) * 100)

                # 先四捨五入為整數，再確保不會低於0%，也不會超過100%
                intimacy_percentage = min(100, max(0, round(raw_percentage)))
            else:
                # 如果已經是最高等級，百分比為100%
                intimacy_percentage = 100

            # 取得目前等級的 key (level_key)，從 levels 中找 title 相符的 key
            level_key = None
            for key, value in levels.items():
                if value.get("title") == current_level:
                    level_key = key
                    break

            # 確保 level_key 是合法的整數字串
            if level_key and level_key.isdigit():
                level_num = int(level_key)
                old_lock_level = old_meta_data.get("lock_level", 0)

                # 如果新的等級比原本大，就更新 lock_level
                if level_num > old_lock_level:
                    new_card = self.get_card_id(levels, level_num, character_id)

                    if new_card is not None:
                        self.logger.info(f"開始更新用戶卡片收集，新卡片ID: {new_card}")

                        try:
                            # 第一步：更新卡片收藏
                            update_result = await self.firebase_service.update_array_field(
                                "user_card_collections", user_id, "collectedCardIds", [new_card])

                            self.logger.info(f"卡片更新完成，結果: {update_result}")

                            # 可以添加結果驗證 (如果 update_array_field 返回結果)
                            # if not update_result.success:
                            #     self.logger.warning(f"卡片更新可能未成功: {update_result}")

                        except Exception as card_err:
                            self.logger.error(f"更新卡片時發生錯誤: {card_err}")
                            # 這裡可以決定是否繼續更新頻道數據
                            # 如果卡片更新失敗但我們仍想繼續更新頻道，就不要 raise

                    self.logger.info(f"解鎖新關卡: {level_num}（原本: {old_lock_level}）")
                else:
                    level_num = old_lock_level
                    self.logger.info(f"已達最高解鎖關卡: {old_lock_level}")

                # 準備新的元數據
                new_meta = {
                    "meta_data": {
                        "intimacy": intimacy,
                        "total_intimacy": total_intimacy,
                        "current_level": current_level,
                        "next_level": next_level,
                        "intimacy_percentage": intimacy_percentage,
                        "lock_level": level_num
                    }
                }

                # 第二步：更新頻道數據
                self.logger.info(f"開始更新頻道數據: {new_meta}")
                await self.fetch_cache_service.update_and_cache_channel_data(user_id=user_id,
                                                                             channel_id=channel_id,
                                                                             new_data=new_meta)
                self.logger.info("頻道數據更新完成")
        except Exception as e:
            self.logger.error(f"更新meta數據時發生錯誤: {e}")
            self.logger.error(traceback.format_exc())

    async def _update_user_persona(self, user_id: str, channel_id: str, user_persona_result: dict) -> None:
        update_user_persona = user_persona_result.get("structured_output", {})
        old_channel_data = await self.fetch_cache_service.fetch_and_cache_channel_data(user_id, channel_id)
        old_user_persona = old_channel_data.get("user_persona", {})

        # 合併
        merged_persona = self.merge_user_persona(old_user_persona, update_user_persona)

        new_meta = {"user_persona": merged_persona}

        # 把合併後的結果存回 cache（或更新 DB）
        await self.fetch_cache_service.update_and_cache_channel_data(user_id, channel_id, new_meta)

    def merge_user_persona(self, old: dict, update: dict) -> dict:
        """
        將 update 中的欄位合併到 old：
        - name, birthday, age, profession, gender：非空時直接覆蓋
        - nickname, personality, likesDislikes：append，且去重
        - promises, importantEvent：append，且去重（以 dict 完整性比對）
        """
        merged = old.copy()

        # 唯一值欄位
        unique_fields = ["name", "birthday", "age", "profession", "gender"]
        for key in unique_fields:
            val = update.get(key)
            if val is not None:
                merged[key] = val

        # 單純字串列表、append 去重
        list_fields = ["nickname", "personality", "likesDislikes"]
        for key in list_fields:
            new_list = update.get(key) or []
            old_list = merged.get(key) or []
            for item in new_list:
                if item not in old_list:
                    old_list.append(item)
            merged[key] = old_list

        # 複雜物件列表、append 去重（以整個 dict 為單位比較）
        obj_list_fields = ["promises", "importantEvent"]
        for key in obj_list_fields:
            new_items = update.get(key) or []
            old_items = merged.get(key) or []
            for item in new_items:
                if item not in old_items:
                    old_items.append(item)
            merged[key] = old_items

        return merged

    def get_card_id(self, levels: dict, level_num: str, character_id: str) -> Optional[str]:
        """
        取得角色特定等級的卡片 ID，格式為 '{character_id}-{level_num}'
        若該等級存在 hasCard 欄位且為 True，則回傳卡片 ID
        
        參數:
            levels: 包含所有等級資訊的字典
            level_num: 要檢查的等級編號字串 (如 "1", "2" 等)
            character_id: 聊天頻道 ID
        
        返回:
            Optional[str]: 卡片 ID 或 None (如果沒有卡片)
        """
        self.logger.warning(f"levels：{levels}")
        try:
            # 檢查等級是否存在
            level_num = str(level_num)
            if level_num not in levels:
                self.logger.warning(f"等級 {level_num} 不存在")
                return None

            # 獲取該等級資訊
            level_info = levels[level_num]

            # 檢查 hasCard 欄位是否存在且為 True
            has_card = level_info.get("hasCard", False)

            if has_card:
                # 格式化卡片 ID
                return f"{character_id}-card-{level_num}"
            else:
                return None
        except Exception as e:
            self.logger.error(f"獲取卡片 ID 時發生錯誤: {e}")
            return None

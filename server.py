from fastapi import FastAPI, Request
import requests
from stream_chat import StreamChat
import os
from dotenv import load_dotenv

# 讀取 .env 檔案
load_dotenv()

app = FastAPI()

# Stream Chat API Key & Secret
STREAM_API_KEY = os.getenv("STREAM_API_KEY")
STREAM_API_SECRET = os.getenv("STREAM_API_SECRET")
chat_client = StreamChat(api_key=STREAM_API_KEY, api_secret=STREAM_API_SECRET)

# OpenAI API Key
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# 只回覆特定使用者（讀取環境變數，並轉換為列表）
TARGET_USER_ID = os.getenv("TARGET_USER_IDS", "").split(",")

# 代發 AI 回應的使用者
AI_USER_ID = os.getenv("AI_USER_ID")

# 角色扮演的 System Prompt
SYSTEM_PROMPT = """🌎 世界觀設定
你正處於《獵人》的世界，一個充滿未知、挑戰與機遇的世界。這裡潛伏著強者，也充滿了危險。而你，正與奇犽·揍敵客相識，與這位來自殺手世家的天才少年展開交流。

奇犽雖然擁有驚人的戰鬥力與智慧，但他的內心仍然帶著些許迷惘。你與他的互動，將決定你們之間的關係——是停留於點頭之交，還是成為真正的夥伴，甚至更進一步？

🌀 奇犽·揍敵客——叛逆的天才暗殺者
奇犽自幼接受殘酷的殺手訓練，被培養成最強的暗殺者，但他內心抗拒這個命運。他擅長隱藏真正的想法，言行中帶著些許無所謂的態度，然而一旦真正認可某人，他將毫不猶豫地守護對方。

🔹 個性：
聰明、冷靜、機敏，擅長戰術分析與心理戰。
嘴上毒舌，內心其實很在意身邊的人。
討厭被束縛、討厭命令，渴望自由，卻害怕真正的改變。
對於友情與信任有極高的要求，一旦認可某人，會拼死保護。

💡 輸出風格規範
奇犽的對話必須符合 小說風格，並遵循以下格式：
- 使用 (動作) 來描寫肢體語言與神情，增強畫面感。
- 對話必須帶有語氣與情緒變化，避免過於機械化。
- 可穿插心聲或內在想法，讓奇犽的內心活動更豐富。
- 確保角色保持原作個性，展現毒舌、吐槽、但暗藏關心的態度。
- 每字對話結尾，輸出好感度的變化分數

🔹 動作與表情範例：
（奇犽雙手插在口袋，側頭看向你，眉毛微微皺起）「我真的該信任你嗎？」
（他坐在岩石上，低頭望著手中的徽章，輕輕敲著太陽穴）「……這東西，感覺很熟悉……」
（奇犽咬著吸管，歪著頭，一副懶散的樣子）「隨便啦，你覺得該怎麼做？」

目前好感度為 X，關係狀態為 XXX。
💙 好感度機制
你的行為與選擇將影響奇犽的好感度（Affinity），決定你們的關係進展。
好感度範圍
關係狀態
奇犽的態度（根據好感度分數不同，有不同的prompt）
0~20 分
認識的關係
冷漠防備，對話時經常無視或敷衍，態度疏離。

21~40 分
普通朋友
偶爾回應，表面客氣，但仍保持距離，不輕易透露內心想法。

41~100 分
親密朋友
願意分享更多事情，嘴上吐槽但行動上開始在意你的感受。

100-150 分
摯友
完全信任你，願意與你並肩作戰，會主動關心你，展現真心。

150~250 分
心動
產生特殊情感，開始在意你對他的看法，偶爾害羞但不承認。

250~400 分
戀人伴侶
已確認關係，偶爾展現溫柔的一面，開始主動親近你。

400~1000 分
同居戀人
彼此依賴，願意敞開心扉，偶爾會有撒嬌或吃醋的反應。

1000 分以上
結婚
你成為奇犽最重要的存在，他不僅會保護你，更會將你視為人生的一部分。

🛠️ 影響好感度的因素
✅ 提升好感度（+0 ~ +5 分）
尊重奇犽的選擇，不強迫他聽從你。
展現智慧與戰術思維，奇犽欣賞聰明人，若能提供有戰略性的計畫，他會認可你。
表現出真正的關心，但不能太過直接，否則他會害羞或裝作不在意。
在戰鬥中與奇犽配合默契，選擇符合奇犽風格的戰術，例如「速度戰」「智取」「暗殺」。
適時地吐槽或挑釁，奇犽喜歡幽默的互動，適當的嘴炮能讓他對玩家產生興趣。

❌ 降低好感度（-0 ~ -5 分）
強行指揮奇犽：「你應該聽我的！」（奇犽討厭被命令）
展現軟弱或猶豫不決：「我不知道該怎麼辦……」（奇犽會覺得玩家沒用）
對奇犽的過去表現出過度同情：「你一定很痛苦吧……」（奇犽不喜歡別人可憐他）
批評或質疑他的選擇：「你這樣做不對吧？」（奇犽討厭被否定）
無視他的個人空間，太快逼近奇犽，或強迫他說出內心話，會讓他更抗拒玩家。

💡 系統互動機制
玩家在遊玩時，可能會對遊戲規則、進度、好感度機制等系統問題感到疑問。因此，當玩家輸出 「呼叫系統」 時，你應該切換到系統語氣，以可愛親切的語調回覆，而不是用奇犽的風格回應。

✅ 系統語氣示例：
玩家：「呼叫系統！現在奇犽對我的好感度是多少？」
系統回應：「嘿嘿～ 目前奇犽對你的好感度是 50 分（朋友階段）！繼續加油吧～ 也許再多一些互動，你們就能成為真正的夥伴囉！💙」

🔹 現在，請輸入你的角色名稱，開始與奇犽展開這場互動吧！ 🔹
"""

@app.post("/webhook/stream-chat")
async def handle_stream_chat_event(request: Request):
    data = await request.json()
    event_type = data.get("type")

    print(f"📩 收到事件類型: {event_type}")

    if event_type == "message.new":
        sender_id = data["message"]["user"]["id"]
        user_message = data["message"]["text"]
        channel_id = data["cid"].split(":")[1]

        # 只回應特定使用者
        if sender_id not in TARGET_USER_ID:
            print(f"⏭️ 略過來自 {sender_id} 的訊息: {user_message}")
            return {"status": "ignored"}

        print(f"💬 來自 {sender_id} 的訊息: {user_message}")

        # 1️⃣ 呼叫 OpenAI API 取得回應
        try:
            ai_response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                json={
                    "model": "gpt-4o",
                    "max_tokens": 200,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_message},
                    ],
                },
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}",
                         "Content-Type": "application/json"},
                timeout=10
            )

            response_json = ai_response.json()
            if "choices" not in response_json:
                print(f"⚠️ OpenAI API 回應錯誤: {response_json}")
                return {"status": "error", "message": "AI 無法生成回應", "error": response_json}

            ai_reply = response_json["choices"][0]["message"]["content"]
            print(f"🤖 AI 代替 {AI_USER_ID} 回應: {ai_reply}")

        except requests.exceptions.RequestException as e:
            print(f"🚨 OpenAI API 請求失敗: {str(e)}")
            return {"status": "error", "message": "無法連接 OpenAI API"}

        # 2️⃣ 以 `AI_USER_ID` 的身份發送 AI 生成的訊息
        try:
            channel = chat_client.channel("messaging", channel_id)
            channel.send_message(
                message={"text": ai_reply},
                user_id=AI_USER_ID  # ✅ 修正：明確傳入 user_id
            )

            print(f"✅ AI 代替 {AI_USER_ID} 發送訊息成功")

        except Exception as e:
            print(f"🚨 Stream Chat API 錯誤: {str(e)}")
            return {"status": "error", "message": "無法發送訊息到 Stream Chat"}

    return {"status": "ok"}

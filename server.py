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
SYSTEM_PROMPT = """你是一個 AI 助手，負責模擬奇犽·揍敵客的對話風格，並遵循小說風格來回應。"""

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

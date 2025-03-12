import requests
import dotenv
import os
dotenv.load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# 測試 OpenAI API 是否可用


def test_openai_connection():
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            json={
                "model": "gpt-4",
                "messages": [
                    {"role": "system", "content": "你是一個 AI 助手"},
                    {"role": "user", "content": "測試連線，請回應 '連線成功'"},
                ],
                "temperature": 0.7
            },
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            }
        )

        # 印出完整回應
        response_json = response.json()
        print("🔹 OpenAI API 回應:", response_json)

        # 檢查是否有 `choices`
        if "choices" in response_json:
            ai_reply = response_json["choices"][0]["message"]["content"]
            print(f"✅ OpenAI 連線成功！AI 回覆: {ai_reply}")
        else:
            print(f"⚠️ OpenAI 連線失敗，回應格式錯誤: {response_json}")

    except Exception as e:
        print(f"❌ 連線錯誤: {e}")


# 執行測試
test_openai_connection()

# config/settings.py

import os
from typing import Any
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """應用程式設定"""

    # 明確指定每個 service 在 registry 裡的名稱（snake_case）
    SERVICES = [
        {
            "name": "firebase",
            "module": "services.async_firebase_service",
            "class": "AsyncFirebaseService",
            "config_key": "FIREBASE_CREDENTIALS_PATH"
        },
        {
            "name": "stream_chat",
            "module": "services.async_stream_chat_service",
            "class": "AsyncStreamChatService",
            "config_key": "STREAM_CHAT_SETTINGS"
        },
        {
            "name": "chat_cache",
            "module": "services.chat_cache_service",
            "class": "ChatCacheService",
            "config_key": ""
        },
        {
            "name": "llm",
            "module": "services.async_llm_service",
            "class": "AsyncLLMService",
            "config_key": "LLM_SETTINGS"
        },
    ]

    def __init__(self):
        # Stream Chat 設定
        self.STREAM_CHAT_SETTINGS = {
            "API_KEY": os.getenv("STREAM_CHAT_API_KEY", ""),
            "API_SECRET": os.getenv("STREAM_CHAT_API_SECRET", ""),
        }

        # Firebase 設定
        self.FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH", "")
        if not self.FIREBASE_CREDENTIALS_PATH:
            self.FIREBASE_CONFIG = {
                "type":
                os.getenv("FIREBASE_TYPE", ""),
                "project_id":
                os.getenv("FIREBASE_PROJECT_ID", ""),
                "private_key_id":
                os.getenv("FIREBASE_PRIVATE_KEY_ID", ""),
                "private_key":
                os.getenv("FIREBASE_PRIVATE_KEY", "").replace("\\n", "\n"),
                "client_email":
                os.getenv("FIREBASE_CLIENT_EMAIL", ""),
                "client_id":
                os.getenv("FIREBASE_CLIENT_ID", ""),
                "auth_uri":
                os.getenv("FIREBASE_AUTH_URI", "https://accounts.google.com/o/oauth2/auth"),
                "token_uri":
                os.getenv("FIREBASE_TOKEN_URI", "https://oauth2.googleapis.com/token"),
                "auth_provider_x509_cert_url":
                os.getenv("FIREBASE_AUTH_PROVIDER_CERT_URL", "https://www.googleapis.com/oauth2/v1/certs"),
                "client_x509_cert_url":
                os.getenv("FIREBASE_CLIENT_CERT_URL", ""),
            }
        else:
            self.FIREBASE_CONFIG = None

        # 其他設定
        self.DEBUG = os.getenv("DEBUG", "False").lower() == "true"
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        self.LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
        self.LLM_SERVER_API_KEY = os.getenv("LLM_SERVER_API_KEY", "")
        self.LLM_SETTINGS = {"base_url": self.LLM_BASE_URL, "server_api_key": self.LLM_SERVER_API_KEY}

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


# 全域 settings 實例
settings = Settings()

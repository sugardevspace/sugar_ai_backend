# services/auto_registry.py

import importlib
import inspect
import logging
from typing import Dict, Any

from config.settings import settings

logger = logging.getLogger(__name__)


class AutoServiceRegistry:

    @staticmethod
    async def load_services_from_config() -> Dict[str, Any]:
        """
        根據 settings.SERVICES 用 snake_case 的 name 註冊 service 實例。
        """
        services: Dict[str, Any] = {}

        for cfg in getattr(settings, "SERVICES", []):
            name = cfg["name"]  # <- snake_case 名稱
            module_str = cfg["module"]
            cls_name = cfg["class"]
            config_key = cfg.get("config_key", "")

            try:
                module = importlib.import_module(module_str)
                service_cls = getattr(module, cls_name)
            except (ImportError, AttributeError) as e:
                logger.error(f"載入 service 類別失敗：{module_str}.{cls_name} — {e}")
                continue

            # 取得對應設定
            cfg_val = getattr(settings, config_key, None) if config_key else None

            # 建立實例
            if cfg_val:
                # 依照不同 config_key 可客製化初始化
                if config_key == "FIREBASE_CREDENTIALS_PATH":
                    instance = service_cls(credentials_path=cfg_val)
                elif config_key == "FIREBASE_CONFIG":
                    instance = service_cls(config=cfg_val)
                elif config_key == "STREAM_CHAT_SETTINGS":
                    instance = service_cls(api_key=cfg_val.get("API_KEY"), api_secret=cfg_val.get("API_SECRET"))
                elif config_key == "LLM_SETTINGS":
                    instance = service_cls(base_url=cfg_val.get("base_url"), api_key=cfg_val.get("server_api_key"))
                else:
                    instance = service_cls()
            else:
                instance = service_cls()

            # 如果有 initialize 方法就呼叫它
            if hasattr(instance, "initialize"):
                init_m = getattr(instance, "initialize")
                if inspect.iscoroutinefunction(init_m):
                    ok = await init_m()
                else:
                    ok = init_m()
                if ok is False:
                    logger.error(f"服務 {name} 初始化失敗")
                    continue

            # 註冊到服務列表
            services[name] = instance
            logger.info(f"成功載入 service：{name}")

        return services

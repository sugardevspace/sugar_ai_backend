# plugins/plugin_manager.py
import os
import importlib
import inspect
from typing import Dict, Any, List, Type, Optional
import logging

from fastapi import Request

from .plugin_base import BasePlugin


class PluginManager:
    """插件管理器：負責插件的發現、載入和生命週期管理"""

    def __init__(self):
        self._plugins = {}  # 存儲已載入的插件實例
        self._services = {}  # 存儲共享服務
        self.logger = logging.getLogger("plugin_manager")

    def register_service(self, name: str, service: Any) -> None:
        """註冊一個服務，供插件使用"""
        self._services[name] = service
        self.logger.info(f"Service registered: {name}")

    def get_service(self, name: str) -> Optional[Any]:
        """取得一個已註冊的服務"""
        return self._services.get(name)

    def discover_plugins(self, plugins_dir: str = "plugins") -> List[Type[BasePlugin]]:
        """在指定目錄發現所有插件類別"""
        plugin_classes = []

        # 確保我們的目錄是絕對路徑
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        plugins_path = os.path.join(base_dir, plugins_dir)

        # 遍歷 plugins 目錄下的所有子目錄
        for item in os.listdir(plugins_path):
            # 忽略非目錄或特殊檔案
            if item.startswith("__") or not os.path.isdir(os.path.join(plugins_path, item)):
                continue

            # 修改這行：構建正確的模組名稱
            module_name = f"{plugins_dir}.{item}.{item}"

            try:
                # 動態導入模組
                module = importlib.import_module(module_name)

                # 尋找模組中的所有類別
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)

                    # 檢查是否是 BasePlugin 的子類 (但不是 BasePlugin 自身)
                    if (inspect.isclass(attr) and issubclass(attr, BasePlugin) and attr != BasePlugin):
                        plugin_classes.append(attr)
                        self.logger.info(f"Discovered plugin: {attr.__name__}")
            except (ImportError, AttributeError) as e:
                self.logger.error(f"Error loading plugin module {module_name}: {e}")

        return plugin_classes

    async def load_plugins(self) -> None:
        plugin_classes = self.discover_plugins()
        for plugin_class in plugin_classes:
            try:
                plugin_instance = plugin_class()
                # 插件初始化為 async
                if hasattr(plugin_instance, "init_plugin") and inspect.iscoroutinefunction(plugin_instance.init_plugin):
                    await plugin_instance.init_plugin(self._services)
                else:
                    plugin_instance.init_plugin(self._services)

                self._plugins[plugin_instance.plugin_name] = plugin_instance
                self.logger.info(f"Plugin loaded: {plugin_instance.plugin_name} v{plugin_instance.version}")
            except Exception as e:
                self.logger.error(f"Error initializing plugin {plugin_class.__name__}: {e}")

    def get_plugin(self, plugin_name: str) -> Optional[BasePlugin]:
        """根據名稱取得插件實例"""
        return self._plugins.get(plugin_name)

    async def list_plugins(self) -> List[Dict[str, Any]]:
        statuses = []
        for name, plugin in self._plugins.items():
            try:
                result = plugin.get_status()
                # 只有是 coroutine/awaitable 才 await
                if inspect.isawaitable(result):
                    result = await result
                # 確保拿到 dict
                if not isinstance(result, dict):
                    raise TypeError(f"{name}.get_status() 必須回傳 dict")
                statuses.append(result)
            except Exception as e:
                self.logger.error(f"載入插件 {name} 狀態失敗：{e}", exc_info=True)
                statuses.append({"name": name, "status": "error", "error": str(e)})
        return statuses

    async def start_all_plugins(self) -> None:
        for plugin_name, plugin in self._plugins.items():
            try:
                if inspect.iscoroutinefunction(plugin.start):
                    await plugin.start()
                else:
                    plugin.start()
                self.logger.info(f"Plugin started: {plugin_name}")
            except Exception as e:
                self.logger.error(f"Error starting plugin {plugin_name}: {e}")

    def stop_all_plugins(self) -> None:
        """停止所有已載入的插件"""
        for plugin_name, plugin in self._plugins.items():
            try:
                plugin.stop()
                self.logger.info(f"Plugin stopped: {plugin_name}")
            except Exception as e:
                self.logger.error(f"Error stopping plugin {plugin_name}: {e}")

    async def handle_event(self,
                           event_type: str,
                           event_data: Dict[str, Any],
                           target_plugin: Optional[str] = None) -> Dict[str, Any]:
        results = {}
        plugins = [self.get_plugin(target_plugin)] if target_plugin else self._plugins.values()

        for plugin in plugins:
            if plugin:
                try:
                    if inspect.iscoroutinefunction(plugin.handle_event):
                        result = await plugin.handle_event(event_type, event_data)
                    else:
                        result = plugin.handle_event(event_type, event_data)
                    results[plugin.plugin_name] = result
                except Exception as e:
                    self.logger.error(f"Plugin error in {plugin.plugin_name}: {e}")
                    results[plugin.plugin_name] = {"error": str(e)}

        return results


# 讓在 core/rounters 可以直接可以直接DI
def get_plugin_manager(request: Request) -> PluginManager:
    return request.app.state.plugin_manager

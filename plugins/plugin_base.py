from abc import ABC, abstractmethod
from typing import Dict, Any


class BasePlugin(ABC):
    def __init__(self):
        self.services = {}
        self.initialized = False
        self.running = False

    @property
    def plugin_name(self) -> str:
        return self.__class__.__name__

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Base plugin description"

    async def init_plugin(self, services: Dict[str, Any]) -> None:
        self.services = services
        self.initialized = True

    async def start(self) -> None:
        if not self.initialized:
            raise RuntimeError(
                f"Plugin {self.plugin_name} has not been initialized")
        self.running = True

    async def stop(self) -> None:
        self.running = False

    @abstractmethod
    async def handle_event(self, event_type: str, event_data: Dict[str, Any]) -> Any:
        pass

    def get_status(self) -> Dict[str, Any]:
        return {
            "name": self.plugin_name,
            "version": self.version,
            "initialized": self.initialized,
            "running": self.running
        }

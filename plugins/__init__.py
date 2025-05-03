# plugins/__init__.py
from .plugin_base import BasePlugin
from .plugin_manager import PluginManager

__all__ = ['BasePlugin', 'PluginManager']
"""
NAS-Tools Plugin Framework v2
"""

from .hook_system import HookSystem
from .registry import PluginRegistry

__all__ = ["PluginRegistry", "HookSystem"]

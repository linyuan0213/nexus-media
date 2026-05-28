"""缓存管理器工厂 — 独立模块避免循环导入.

将 get_cache_manager 提取到独立模块，避免在 cache_system/__init__.py
初始化过程中被其他模块间接触发循环导入。
"""

from .cache_manager import CacheManager

_global_cache_manager = None


def get_cache_manager() -> CacheManager:
    """获取全局缓存管理器实例."""
    global _global_cache_manager
    if _global_cache_manager is None:
        _global_cache_manager = CacheManager()
    return _global_cache_manager

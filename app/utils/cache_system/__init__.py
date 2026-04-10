# -*- coding: utf-8 -*-
"""
统一缓存系统

提供统一的缓存接口，支持多种后端存储（内存、Redis等）
"""

from .cache_manager import CacheManager
from .adapters import MemoryCacheAdapter, RedisCacheAdapter
from .decorators import cached, cached_with_lock, lru_cache_with_ttl
from .caches import (
    TMDBCache,
    MediaInfoCache,
    SearchResultCache,
    TokenCache,
    ConfigLoadCache,
    CategoryLoadCache,
    OpenAISessionCache,
    SiteInfoCache,
)
from .utils import CacheKeyBuilder
from .warmer import (
    CacheWarmer,
    ConfigCacheWarmer,
    SiteCacheWarmer,
    WordsCacheWarmer,
    TMDBTrendingWarmer,
    CacheWarmerManager,
    get_warmer_manager,
    warm_cache_on_startup,
)
from .events import (
    CacheEventType,
    CacheEvent,
    CacheEventListener,
    CacheEventManager,
    get_event_manager,
    on_cache_event,
)

__all__ = [
    # 核心管理器
    'CacheManager',
    # 适配器
    'MemoryCacheAdapter',
    'RedisCacheAdapter',
    # 装饰器
    'cached',
    'cached_with_lock',
    'lru_cache_with_ttl',
    # 专用缓存
    'TMDBCache',
    'MediaInfoCache',
    'SearchResultCache',
    'TokenCache',
    'ConfigLoadCache',
    'CategoryLoadCache',
    'OpenAISessionCache',
    'SiteInfoCache',
    # 工具
    'CacheKeyBuilder',
    # 缓存预热
    'CacheWarmer',
    'ConfigCacheWarmer',
    'SiteCacheWarmer',
    'WordsCacheWarmer',
    'TMDBTrendingWarmer',
    'CacheWarmerManager',
    'get_warmer_manager',
    'warm_cache_on_startup',
    # 缓存事件
    'CacheEventType',
    'CacheEvent',
    'CacheEventListener',
    'CacheEventManager',
    'get_event_manager',
    'on_cache_event',
]

# 全局缓存管理器实例
_global_cache_manager = None


def get_cache_manager() -> CacheManager:
    """获取全局缓存管理器实例"""
    global _global_cache_manager
    if _global_cache_manager is None:
        _global_cache_manager = CacheManager()
    return _global_cache_manager

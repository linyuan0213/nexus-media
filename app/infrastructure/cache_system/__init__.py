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
from .compat import cacheman

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
    # 专用缓存类
    'TMDBCache',
    'MediaInfoCache',
    'SearchResultCache',
    'TokenCache',
    'ConfigLoadCache',
    'CategoryLoadCache',
    'OpenAISessionCache',
    'SiteInfoCache',
    # 专用缓存实例
    'MediaInfoCache',
    'SearchResultCache',
    'SiteInfoCache',
    'TokenCache',
    'ConfigLoadCache',
    'CategoryLoadCache',
    'OpenAISessionCache',
    # 工具
    'CacheKeyBuilder',
    'get_cache_manager',
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
    # 兼容旧接口
    'cacheman',
]

# 全局缓存管理器实例
_global_cache_manager = None


def get_cache_manager() -> CacheManager:
    """获取全局缓存管理器实例"""
    global _global_cache_manager
    if _global_cache_manager is None:
        _global_cache_manager = CacheManager()
    return _global_cache_manager


# 初始化全局缓存管理器并创建默认缓存
_cache_manager = get_cache_manager()
_cache_manager.create_memory_cache("tmdb_supply", maxsize=500)
_cache_manager.create_memory_cache("media_info", maxsize=1000)
_cache_manager.create_memory_cache("search_result", maxsize=500)
_cache_manager.create_memory_cache("token", maxsize=512)
_cache_manager.create_memory_cache("config_load", maxsize=1)
_cache_manager.create_memory_cache("category_load", maxsize=2)
_cache_manager.create_memory_cache("openai_session", maxsize=200)
_cache_manager.create_memory_cache("site_info", maxsize=100)
_cache_manager.create_redis_cache("tmdb")

# 创建专用缓存实例
MediaInfoCache = MediaInfoCache(_cache_manager.get("media_info"))
SearchResultCache = SearchResultCache(_cache_manager.get("search_result"))
SiteInfoCache = SiteInfoCache(_cache_manager.get("site_info"))
TokenCache = TokenCache(_cache_manager.get("token"))
ConfigLoadCache = ConfigLoadCache(_cache_manager.get("config_load"))
CategoryLoadCache = CategoryLoadCache(_cache_manager.get("category_load"))
OpenAISessionCache = OpenAISessionCache(_cache_manager.get("openai_session"))

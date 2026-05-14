"""
兼容性模块 - 兼容旧的缓存接口

这个模块提供了对旧版缓存API的兼容支持，方便逐步迁移
"""

from .adapters import MemoryCacheAdapter, RedisCacheAdapter
from .caches import (
    CategoryLoadCache as NewCategoryLoadCache,
    ConfigLoadCache as NewConfigLoadCache,
    OpenAISessionCache as NewOpenAISessionCache,
    TMDBCache as NewTMDBCache,
    TokenCache as NewTokenCache,
)


# 兼容旧的 cacheman
class CacheManagerCompat:
    """兼容旧的 CacheManager"""

    def __init__(self):
        self._adapters = {}
        self._init_default_caches()

    def _init_default_caches(self):
        """初始化默认缓存"""
        # tmdb_supply 缓存
        self._adapters["tmdb_supply"] = MemoryCacheAdapter(maxsize=500, name="tmdb_supply")

    def __getitem__(self, name: str):
        """支持 cacheman['name'] 访问"""
        if name not in self._adapters:
            self._adapters[name] = MemoryCacheAdapter(maxsize=100, name=name)
        return self._adapters[name]

    def get(self, name: str, default=None):
        """获取缓存适配器"""
        return self._adapters.get(name, default)


# 全局兼容实例
cacheman = CacheManagerCompat()

# 兼容旧的缓存实例
TokenCache = NewTokenCache()
ConfigLoadCache = NewConfigLoadCache()
CategoryLoadCache = NewCategoryLoadCache()
OpenAISessionCache = NewOpenAISessionCache()

# 新增缓存实例（兼容旧导入）
MediaInfoCache = None  # 在 utils/__init__.py 中初始化
SearchResultCache = None
SiteInfoCache = None


# 兼容旧的 TMDBCache 接口
class TMDBCacheCompat(NewTMDBCache):
    """
    兼容旧的 TMDBCache 接口

    保持与旧版 app.utils.tmdb_cache.TMDBCache 相同的API
    """

    def __init__(self):
        # 使用Redis适配器
        adapter = RedisCacheAdapter(name="tmdb_compat")
        super().__init__(adapter)


# 创建兼容实例
TMDBCache = TMDBCacheCompat()


# 兼容旧的装饰器
def cached(cache_instance, key_func=None):
    """兼容旧的 cached 装饰器"""
    from .decorators import cached as new_cached

    return new_cached(cache_instance, key_func=key_func)


def cached_with_lock(cache_instance, lock=None):
    """兼容旧的 cached_with_lock 装饰器"""
    from .decorators import cached_with_lock as new_cached_with_lock

    return new_cached_with_lock(cache_instance, lock=lock)

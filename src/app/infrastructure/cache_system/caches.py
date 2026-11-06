"""
专用缓存类
提供针对特定业务场景的缓存封装
"""

from typing import Any

from .adapters import MemoryCacheAdapter
from .base import CacheAdapter


class TypedCache:
    """类型化缓存基类"""

    def __init__(self, adapter: CacheAdapter):
        self._adapter = adapter

    def get(self, key: str) -> Any | None:
        return self._adapter.get(key)

    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        return self._adapter.set(key, value, ttl)

    def delete(self, key: str) -> bool:
        return self._adapter.delete(key)

    def exists(self, key: str) -> bool:
        return self._adapter.exists(key)

    def clear(self) -> bool:
        return self._adapter.clear()

    def get_stats(self) -> dict[str, Any]:
        return self._adapter.get_stats()


class MediaInfoCache(TypedCache):
    """媒体信息缓存"""

    # 默认 TTL：24 小时
    DEFAULT_TTL = 24 * 3600

    def __init__(self, adapter: CacheAdapter | None = None):
        if adapter is None:
            adapter = MemoryCacheAdapter(maxsize=1000, name="media_info", default_ttl=self.DEFAULT_TTL)
        super().__init__(adapter)

    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """设置媒体信息缓存，默认 TTL 24 小时."""
        ttl = ttl or self.DEFAULT_TTL
        return super().set(key, value, ttl)


class SearchResultCache(TypedCache):
    """搜索结果缓存"""

    # 默认 TTL：1 小时
    DEFAULT_TTL = 3600

    def __init__(self, adapter: CacheAdapter | None = None):
        if adapter is None:
            adapter = MemoryCacheAdapter(maxsize=500, name="search_result", default_ttl=self.DEFAULT_TTL)
        super().__init__(adapter)

    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """设置搜索结果缓存，默认 TTL 1 小时."""
        ttl = ttl or self.DEFAULT_TTL
        return super().set(key, value, ttl)


class TokenCache(TypedCache):
    """Token缓存"""

    # 默认 TTL：7 天
    DEFAULT_TTL = 7 * 24 * 3600

    def __init__(self, adapter: CacheAdapter | None = None):
        if adapter is None:
            adapter = MemoryCacheAdapter(maxsize=512, name="token", default_ttl=self.DEFAULT_TTL)
        super().__init__(adapter)

    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """设置 Token 缓存，默认 TTL 7 天."""
        ttl = ttl or self.DEFAULT_TTL
        return super().set(key, value, ttl)


class RBACSnapshotCache(TypedCache):
    """RBAC 用户权限快照缓存（权限码 + 角色码），授权变更时主动失效"""

    # 默认 TTL：60 秒（权限回收时效兜底，主动失效为主要路径）
    DEFAULT_TTL = 60

    def __init__(self, adapter: CacheAdapter | None = None):
        if adapter is None:
            adapter = MemoryCacheAdapter(maxsize=1024, name="rbac_auth_snapshot", default_ttl=self.DEFAULT_TTL)
        super().__init__(adapter)

    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """设置权限快照缓存，默认 TTL 60 秒."""
        ttl = ttl or self.DEFAULT_TTL
        return super().set(key, value, ttl)


class ConfigLoadCache(TypedCache):
    """配置加载缓存"""

    # 默认 TTL：10 分钟
    DEFAULT_TTL = 600

    def __init__(self, adapter: CacheAdapter | None = None):
        if adapter is None:
            adapter = MemoryCacheAdapter(maxsize=1, name="config_load", default_ttl=self.DEFAULT_TTL)
        super().__init__(adapter)

    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """设置配置加载缓存，默认 TTL 10 分钟."""
        ttl = ttl or self.DEFAULT_TTL
        return super().set(key, value, ttl)


class CategoryLoadCache(TypedCache):
    """分类加载缓存"""

    # 默认 TTL：10 分钟
    DEFAULT_TTL = 600

    def __init__(self, adapter: CacheAdapter | None = None):
        if adapter is None:
            adapter = MemoryCacheAdapter(maxsize=2, name="category_load", default_ttl=self.DEFAULT_TTL)
        super().__init__(adapter)

    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """设置分类加载缓存，默认 TTL 10 分钟."""
        ttl = ttl or self.DEFAULT_TTL
        return super().set(key, value, ttl)


class OpenAISessionCache(TypedCache):
    """OpenAI会话缓存"""

    # 默认 TTL：30 天
    DEFAULT_TTL = 30 * 24 * 3600

    def __init__(self, adapter: CacheAdapter | None = None):
        if adapter is None:
            adapter = MemoryCacheAdapter(maxsize=200, name="openai_session", default_ttl=self.DEFAULT_TTL)
        super().__init__(adapter)

    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """设置 OpenAI 会话缓存，默认 TTL 30 天."""
        ttl = ttl or self.DEFAULT_TTL
        return super().set(key, value, ttl)


class SiteInfoCache(TypedCache):
    """站点信息缓存"""

    # 默认 TTL：6 小时
    DEFAULT_TTL = 6 * 3600

    def __init__(self, adapter: CacheAdapter | None = None):
        if adapter is None:
            adapter = MemoryCacheAdapter(maxsize=100, name="site_info", default_ttl=self.DEFAULT_TTL)
        super().__init__(adapter)

    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """设置站点信息缓存，默认 TTL 6 小时."""
        ttl = ttl or self.DEFAULT_TTL
        return super().set(key, value, ttl)


class WordsProcessCache(TypedCache):
    """识别词处理缓存"""

    # 默认 TTL：24 小时
    DEFAULT_TTL = 24 * 3600

    def __init__(self, adapter: CacheAdapter | None = None):
        if adapter is None:
            adapter = MemoryCacheAdapter(maxsize=1000, name="words_process", default_ttl=self.DEFAULT_TTL)
        super().__init__(adapter)

    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """设置识别词处理缓存，默认 TTL 24 小时."""
        ttl = ttl or self.DEFAULT_TTL
        return super().set(key, value, ttl)

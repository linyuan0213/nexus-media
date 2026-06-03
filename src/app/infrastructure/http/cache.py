"""HTTP 响应缓存配置."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class HttpCacheConfig:
    """HTTP 客户端缓存配置.

    通过 CacheManager 按名称管理缓存适配器（默认 tiered：内存 + Redis 二级缓存），
    HttpClient 在 request() 层自动进行缓存读写。

    为避免循环导入（cache.py ↔ cache_system），_adapter 由调用方注入，
    构造时通过 get_cache_manager() 创建后传入。
    """

    cache_name: str = "http"
    default_ttl: int = 300
    cache_methods: tuple[str, ...] = ("GET",)
    max_value_size: int = 10 * 1024 * 1024

    _adapter: Any = field(default=None, init=False, repr=False)

    def set_adapter(self, adapter: Any) -> None:
        self._adapter = adapter

    def get(self, key: str) -> Any | None:
        return self._adapter.get(key) if self._adapter else None

    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        if not self._adapter:
            return False
        return self._adapter.set(key, value, ttl=ttl)

    def is_cacheable(self, method: str, response: Any) -> bool:
        if method not in self.cache_methods:
            return False
        if response.status_code != 200:
            return False
        if len(response.content) > self.max_value_size:
            return False
        return True

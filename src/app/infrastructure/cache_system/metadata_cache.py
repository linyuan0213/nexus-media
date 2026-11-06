"""统一元数据缓存.

所有 provider 的详情、搜索、分集、人物等元数据共用同一个 tiered 缓存命名空间，
通过 kind/provider 维度隔离，禁止再为单个 provider 建独立缓存实例。
"""

from __future__ import annotations

from typing import Any

from app.infrastructure.cache_system.manager import get_cache_manager

CACHE_NAME = "metadata"


class MetadataCache:
    """统一元数据缓存访问器."""

    def __init__(self, prefix: str = "", adapter: Any | None = None):
        self._adapter = adapter or get_cache_manager().get_or_create(
            CACHE_NAME,
            cache_type="tiered",
            maxsize=2000,
            ttl=600,
        )
        self._prefix = str(prefix or "").strip(":")

    @property
    def adapter(self) -> Any:
        return self._adapter

    @staticmethod
    def _type_key(media_type: Any) -> str:
        value = media_type.value if hasattr(media_type, "value") else str(media_type or "auto")
        return "tv" if value == "anime" else value

    def _key(self, key: str) -> str:
        return f"{self._prefix}:{key}" if self._prefix else str(key)

    def get(self, key: str) -> Any | None:
        return self._adapter.get(self._key(key))

    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        return self._adapter.set(self._key(key), value, ttl)

    def delete(self, key: str) -> bool:
        return self._adapter.delete(self._key(key))

    def exists(self, key: str) -> bool:
        return self._adapter.exists(self._key(key))

    def clear(self) -> bool:
        pattern = f"{self._prefix}:*" if self._prefix else "*"
        for key in self._adapter.keys(pattern):
            self._adapter.delete(key)
        return True

    TTL_DETAIL = 7 * 24 * 3600
    TTL_MEDIA = 24 * 3600
    TTL_SEASON = 12 * 3600
    TTL_TRENDING = 2 * 3600

    def get_detail(
        self,
        provider: str,
        external_id: str | int | None,
        media_type: Any = "auto",
        language: str | None = None,
        extra: str = "",
        version: str = "3",
        scope: str = "default",
    ) -> Any | None:
        if external_id in (None, ""):
            return None
        type_key = self._type_key(media_type)
        return self.get(self.detail_key(provider, external_id, type_key, language, extra, version, scope))

    def set_detail(
        self,
        provider: str,
        external_id: str | int | None,
        info: Any,
        media_type: Any = "auto",
        language: str | None = None,
        ttl: int | None = None,
        extra: str = "",
        version: str = "3",
        scope: str = "default",
    ) -> bool:
        if external_id in (None, "") or not info:
            return False
        type_key = self._type_key(media_type)
        return self.set(
            self.detail_key(provider, external_id, type_key, language, extra, version, scope),
            info,
            ttl or self.TTL_DETAIL,
        )

    def get_season(self, provider: str, external_id: str | int, season: int) -> Any | None:
        return self.get(f"season:{str(provider).lower()}:{external_id}:{int(season)}")

    def set_season(self, provider: str, external_id: str | int, season: int, info: Any, ttl: int | None = None) -> bool:
        return self.set(
            f"season:{str(provider).lower()}:{external_id}:{int(season)}",
            info,
            ttl or self.TTL_SEASON,
        )

    def get_trending(self, provider: str, media_type: str, time_window: str, page: int = 1) -> Any | None:
        return self.get(f"trending:{str(provider).lower()}:{media_type}:{time_window}:{int(page)}")

    def set_trending(
        self,
        provider: str,
        media_type: str,
        time_window: str,
        page: int,
        info: Any,
        ttl: int | None = None,
    ) -> bool:
        return self.set(
            f"trending:{str(provider).lower()}:{media_type}:{time_window}:{int(page)}",
            info,
            ttl or self.TTL_TRENDING,
        )

    def get_media(self, title: str, year: str | None = None, media_type: Any = None) -> Any | None:
        type_key = self._type_key(media_type) if media_type else ""
        return self.get(f"media:3:{title}:{year or ''}:{type_key}")

    def set_media(
        self,
        title: str,
        info: Any,
        year: str | None = None,
        media_type: Any = None,
        ttl: int | None = None,
    ) -> bool:
        type_key = self._type_key(media_type) if media_type else ""
        return self.set(f"media:3:{title}:{year or ''}:{type_key}", info, ttl or self.TTL_MEDIA)

    def clear_provider(self, provider: str) -> bool:
        provider_key = str(provider or "").lower()
        patterns = (
            f"detail:*:{provider_key}:*",
            f"season:{provider_key}:*",
            f"trending:{provider_key}:*",
        )
        for pattern in patterns:
            for key in self._adapter.keys(self._key(pattern)):
                self._adapter.delete(key)
        return True

    @staticmethod
    def detail_key(
        provider: str,
        external_id: str | int,
        media_type: str = "auto",
        language: str | None = None,
        extra: str = "",
        version: str = "3",
        scope: str = "default",
    ) -> str:
        return (
            f"detail:{version}:{str(provider or '').lower()}:{str(media_type or 'auto')}:"
            f"{external_id}:{scope or 'default'}:{language or 'default'}:{extra}"
        )

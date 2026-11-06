"""元数据网关：统一上下文、缓存键和 singleflight 的入口边界。"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal

from app.domain.mediatypes import MediaType


@dataclass(frozen=True)
class MetadataContext:
    user_id: int | None = None
    permissions: frozenset[str] = frozenset()
    content_profile: str = "default"
    policy_key: str = "default"
    purpose: str = "api"
    allow_private: bool = False
    language: str = ""
    request_id: str = ""


@dataclass
class MetadataEnvelope:
    provider: str
    external_id: str
    media_type: MediaType | None
    metadata: dict[str, Any]
    fetched_at: datetime
    expires_at: datetime
    refs: list[Any] = field(default_factory=list)
    identity_id: str | None = None
    snapshot_id: str | None = None
    cache_hit: bool = False
    stale: bool = False
    degraded: bool = False


class MetadataGateway:
    """对业务层暴露的唯一元数据读取门面。

    当前委托 MetadataService 的已实现能力；迁移期间不改变旧调用。
    """

    def __init__(self, service: Any, *, default_ttl: int = 600):
        self._service = service
        self._default_ttl = default_ttl
        self._cache: dict[str, tuple[float, MetadataEnvelope]] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _lock_for(self, key: str) -> threading.Lock:
        with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._locks[key] = lock
            return lock

    @staticmethod
    def _key(
        provider: str,
        external_id: str,
        media_type: MediaType | None,
        context: MetadataContext,
        season: int,
    ) -> str:
        type_key = media_type.value if media_type else "auto"
        return (
            f"{provider}:{external_id}:{type_key}:{season}:"
            f"{context.content_profile}:{context.policy_key}:{context.language}:{context.allow_private}"
        )

    def resolve(
        self,
        provider: str,
        external_id: str,
        *,
        context: MetadataContext,
        media_type: MediaType | None = None,
        season: int = 0,
        ttl: int | None = None,
        freshness: Literal["default", "force"] = "default",
    ) -> MetadataEnvelope | None:
        key = self._key(provider, external_id, media_type, context, season)
        if freshness == "default":
            cached = self._cache.get(key)
            if cached and cached[0] > time.monotonic():
                envelope = cached[1]
                envelope.cache_hit = True
                return envelope

        lock = self._lock_for(key)
        with lock:
            if freshness == "default":
                cached = self._cache.get(key)
                if cached and cached[0] > time.monotonic():
                    envelope = cached[1]
                    envelope.cache_hit = True
                    return envelope
            data = self._service.compose_for_ref(
                provider,
                external_id,
                media_type=media_type or MediaType.UNKNOWN,
                content_profile=context.content_profile,
                allow_private=context.allow_private,
                permissions=set(context.permissions),
                user_id=context.user_id,
                max_age_seconds=0 if freshness == "force" else int((ttl or self._default_ttl) * 0.8),
            )
            if not isinstance(data, dict):
                return None
            now = datetime.now()
            envelope = MetadataEnvelope(
                provider=provider,
                external_id=str(external_id),
                media_type=media_type,
                metadata=data,
                fetched_at=now,
                expires_at=now + timedelta(seconds=ttl or self._default_ttl),
            )
            self._cache[key] = (time.monotonic() + (ttl or self._default_ttl), envelope)
            return envelope

    def resolve_many(
        self,
        refs: list[tuple[str, str]],
        *,
        context: MetadataContext,
        media_type: MediaType | None = None,
        season: int = 0,
    ) -> dict[tuple[str, str], MetadataEnvelope | None]:
        out: dict[tuple[str, str], MetadataEnvelope | None] = {}
        for provider, external_id in dict.fromkeys(refs):
            out[(provider, external_id)] = self.resolve(
                provider,
                external_id,
                context=context,
                media_type=media_type,
                season=season,
            )
        return out

    def clear(self) -> None:
        self._cache.clear()

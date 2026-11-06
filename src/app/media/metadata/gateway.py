"""元数据网关：统一上下文、缓存键和 singleflight 的入口边界。"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field, replace
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

    @classmethod
    def from_user(
        cls,
        user: Any,
        *,
        purpose: str = "api",
        content_profile: str = "default",
        policy_key: str = "default",
        allow_private: bool | None = None,
        language: str = "",
        request_id: str = "",
    ) -> MetadataContext:
        permissions = frozenset(getattr(user, "permissions", ()) or ())
        if allow_private is None:
            allow_private = bool(getattr(user, "is_superadmin", False)) or "metadata:private:view" in permissions
        return cls(
            user_id=getattr(user, "user_id", None),
            permissions=permissions,
            content_profile=content_profile or "default",
            policy_key=policy_key or "default",
            purpose=purpose,
            allow_private=bool(allow_private),
            language=language,
            request_id=request_id,
        )


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

    内部委托 MetadataService，统一注入上下文、L1 缓存和同 ref 请求合并。
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
        mode: str,
        provider: str,
        external_id: str,
        media_type: MediaType | None,
        context: MetadataContext,
        scope: str,
        season: int,
    ) -> str:
        type_key = media_type.value if media_type else "auto"
        permission_key = ",".join(sorted(context.permissions))
        return (
            f"{mode}:{provider}:{external_id}:{type_key}:{scope}:{season}:"
            f"{context.content_profile}:{context.policy_key}:{context.language}:"
            f"{context.allow_private}:{permission_key}"
        )

    @staticmethod
    def _scope(season: int, scope: str | None) -> str:
        if scope:
            return scope
        return f"season={season}" if season else "default"

    def _identity_fields(
        self,
        provider: str,
        external_id: str,
        *,
        media_type: MediaType | None,
        scope: str,
    ) -> tuple[str | None, str | None, list[Any]]:
        identity_id = None
        snapshot_id = None
        refs: list[Any] = []
        try:
            lookup = getattr(self._service, "find_identity_id", None)
            if callable(lookup):
                found = lookup(
                    provider,
                    external_id,
                    scope=scope,
                    media_type=media_type.value if media_type else None,
                )
                identity_id = str(found) if found else None
        except Exception:  # noqa: BLE001 - 身份索引失败不影响读取
            identity_id = None
        if identity_id:
            try:
                latest = getattr(self._service, "latest_snapshot_record", None)
                if callable(latest):
                    record = latest(identity_id, scope=scope)
                    snapshot_id = str(getattr(record, "ID", "") or "") or None
            except Exception:  # noqa: BLE001 - 快照索引失败不影响读取
                snapshot_id = None
        return identity_id, snapshot_id, refs

    def _cached(self, key: str) -> MetadataEnvelope | None:
        cached = self._cache.get(key)
        if cached and cached[0] > time.monotonic():
            return replace(cached[1], cache_hit=True)
        return None

    def _stale(self, key: str) -> MetadataEnvelope | None:
        cached = self._cache.get(key)
        if cached:
            return replace(cached[1], cache_hit=True, stale=True, degraded=True)
        return None

    def resolve(
        self,
        provider: str,
        external_id: str,
        *,
        context: MetadataContext | None = None,
        media_type: MediaType | None = None,
        season: int = 0,
        scope: str | None = None,
        ttl: int | None = None,
        freshness: Literal["default", "force"] = "default",
        with_episodes: bool = True,
        max_age_seconds: int | None = None,
    ) -> MetadataEnvelope | None:
        ctx = context or MetadataContext()
        snapshot_scope = self._scope(season, scope)
        key = self._key("resolve", provider, external_id, media_type, ctx, snapshot_scope, season)
        if freshness == "default":
            cached = self._cached(key)
            if cached is not None:
                return cached

        lock = self._lock_for(key)
        with lock:
            if freshness == "default":
                cached = self._cached(key)
                if cached is not None:
                    return cached
            try:
                data = self._service.compose_for_ref(
                    provider,
                    external_id,
                    media_type=media_type or MediaType.UNKNOWN,
                    content_profile=ctx.content_profile,
                    allow_private=ctx.allow_private,
                    permissions=set(ctx.permissions),
                    user_id=ctx.user_id,
                    max_age_seconds=(
                        0
                        if freshness == "force"
                        else max_age_seconds
                        if max_age_seconds is not None
                        else int((ttl or self._default_ttl) * 0.8)
                    ),
                    with_episodes=with_episodes,
                )
            except Exception:
                stale = self._stale(key)
                if stale is not None:
                    return stale
                raise
            if not isinstance(data, dict):
                return self._stale(key)
            now = datetime.now()
            identity_id, snapshot_id, _ = self._identity_fields(
                provider,
                external_id,
                media_type=media_type,
                scope=snapshot_scope,
            )
            refs = data.get("refs") if isinstance(data.get("refs"), list) else []
            envelope = MetadataEnvelope(
                provider=provider,
                external_id=str(external_id),
                media_type=media_type,
                metadata=data,
                fetched_at=now,
                expires_at=now + timedelta(seconds=ttl or self._default_ttl),
                refs=list(refs or []),
                identity_id=identity_id,
                snapshot_id=snapshot_id,
            )
            self._cache[key] = (time.monotonic() + (ttl or self._default_ttl), envelope)
            return envelope

    def lookup(
        self,
        provider: str,
        external_id: str,
        *,
        context: MetadataContext | None = None,
        media_type: MediaType | None = None,
        scope: str = "default",
        content_profile: str | None = None,
        ttl: int | None = None,
        freshness: Literal["default", "force"] = "default",
    ) -> dict[str, Any] | None:
        """按 ref 读取 provider 详情；同 ref 并发只触发一次 provider 调用。"""
        ctx = context or MetadataContext(content_profile=content_profile or "default")
        profile = content_profile or ctx.content_profile
        key_ctx = ctx if profile == ctx.content_profile else replace(ctx, content_profile=profile)
        key = self._key("lookup", provider, external_id, media_type, key_ctx, scope, 0)
        if freshness == "default":
            cached = self._cached(key)
            if cached is not None:
                return cached.metadata

        lock = self._lock_for(key)
        with lock:
            if freshness == "default":
                cached = self._cached(key)
                if cached is not None:
                    return cached.metadata
            try:
                data = self._service.lookup(
                    provider,
                    str(external_id),
                    media_type=media_type,
                    scope=scope,
                    allow_private=ctx.allow_private,
                    content_profile=profile,
                    permissions=set(ctx.permissions),
                )
            except Exception:
                stale = self._stale(key)
                if stale is not None:
                    return stale.metadata
                raise
            if not isinstance(data, dict):
                stale = self._stale(key)
                return stale.metadata if stale is not None else None
            now = datetime.now()
            identity_id, snapshot_id, _ = self._identity_fields(
                provider,
                external_id,
                media_type=media_type,
                scope=scope,
            )
            refs = data.get("refs") if isinstance(data.get("refs"), list) else []
            envelope = MetadataEnvelope(
                provider=provider,
                external_id=str(external_id),
                media_type=media_type,
                metadata=data,
                fetched_at=now,
                expires_at=now + timedelta(seconds=ttl or self._default_ttl),
                refs=list(refs or []),
                identity_id=identity_id,
                snapshot_id=snapshot_id,
            )
            self._cache[key] = (time.monotonic() + (ttl or self._default_ttl), envelope)
            return data

    def resolve_many(
        self,
        refs: list[tuple[str, str]],
        *,
        context: MetadataContext | None = None,
        media_type: MediaType | None = None,
        season: int = 0,
        scope: str | None = None,
    ) -> dict[tuple[str, str], MetadataEnvelope | None]:
        out: dict[tuple[str, str], MetadataEnvelope | None] = {}
        for provider, external_id in dict.fromkeys(refs):
            out[(provider, external_id)] = self.resolve(
                provider,
                external_id,
                context=context,
                media_type=media_type,
                season=season,
                scope=scope,
            )
        return out

    def search(
        self,
        *,
        query: str,
        context: MetadataContext | None = None,
        provider: str | None = None,
        media_type: MediaType | None = None,
        content_profile: str | None = None,
        limit: int = 20,
        wait_timeout: float | None = None,
    ) -> list[dict[str, Any]]:
        ctx = context or MetadataContext(content_profile=content_profile or "default")
        return self._service.search(
            query=query,
            provider=provider,
            media_type=media_type,
            content_profile=content_profile or ctx.content_profile,
            limit=limit,
            allow_private=ctx.allow_private,
            permissions=set(ctx.permissions),
            wait_timeout=wait_timeout,
        )

    def list_providers(
        self,
        *,
        context: MetadataContext | None = None,
        allow_private: bool | None = None,
        permissions: set[str] | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        ctx = context or MetadataContext(
            permissions=frozenset(permissions or ()),
            allow_private=bool(allow_private),
        )
        return self._service.list_providers(
            allow_private=ctx.allow_private,
            permissions=set(ctx.permissions),
            **kwargs,
        )

    def episodes(
        self,
        provider: str,
        external_id: str,
        season: int = 1,
        *,
        context: MetadataContext | None = None,
        media_type: MediaType | None = None,
    ) -> list[dict[str, Any]]:
        ctx = context or MetadataContext()
        kwargs: dict[str, Any] = {
            "allow_private": ctx.allow_private,
            "permissions": set(ctx.permissions),
        }
        return self._service.episodes(provider, str(external_id), season, **kwargs)

    def hydrate_media(self, media_info: Any, *, context: MetadataContext | None = None) -> bool:
        ctx = context or MetadataContext(purpose="hydrate", allow_private=True)
        self._ensure_visible(media_info, ctx)
        return bool(self._service.hydrate_media(media_info))

    def identify_anchor(
        self,
        media_info: Any,
        *,
        context: MetadataContext | None = None,
        policy: str | None = None,
    ) -> bool:
        return bool(self._service.identify_anchor(media_info, policy=policy))

    def compose_for_media(
        self,
        media_info: Any,
        *,
        context: MetadataContext | None = None,
        policy: str | None = None,
        anchor_provider: str | None = None,
        content_profile: str | None = None,
        with_episodes: bool = False,
        persist: bool = False,
        max_age_seconds: int = 0,
        locked: dict[str, Any] | None = None,
        refs_override: list[Any] | None = None,
    ) -> Any:
        ctx = context or MetadataContext(purpose="compose")
        return self._service.compose_for_media(
            media_info,
            policy=policy,
            anchor_provider=anchor_provider,
            content_profile=content_profile,
            with_episodes=with_episodes,
            persist=persist,
            max_age_seconds=max_age_seconds,
            locked=locked,
            user_id=ctx.user_id,
            refs_override=refs_override,
        )

    def latest_snapshot_for_media(self, media_info: Any, *, context: MetadataContext | None = None) -> Any:
        ctx = context or MetadataContext(purpose="snapshot")
        self._ensure_visible(media_info, ctx)
        return self._service.latest_snapshot_for_media(media_info)

    def resolve_season_episode_count(
        self,
        *,
        context: MetadataContext | None = None,
        provider: str,
        external_id: str,
        title: str,
        year: str | None = None,
        media_type: MediaType = MediaType.TV,
        season: int = 1,
        content_profile: str | None = None,
    ) -> int:
        ctx = context or MetadataContext(content_profile=content_profile or "default")
        return int(
            self._service.resolve_season_episode_count(
                provider=provider,
                external_id=external_id,
                title=title,
                year=year,
                media_type=media_type,
                season=season,
                content_profile=content_profile or ctx.content_profile,
                allow_private=ctx.allow_private,
                permissions=set(ctx.permissions),
            )
        )

    def _ensure_visible(self, media_info: Any, context: MetadataContext) -> None:
        descriptor_of = getattr(self._service, "provider_descriptor", None)
        if not callable(descriptor_of):
            return
        provider = str(getattr(media_info, "anchor_provider", "") or "")
        if not provider:
            return
        descriptor = descriptor_of(provider)
        if descriptor is None or getattr(descriptor, "visibility", "public") != "private":
            return
        if not context.allow_private:
            raise PermissionError(f"缺少私有元数据访问权限: {provider}")
        required = str(getattr(descriptor, "required_permission", "") or "metadata:private:view")
        if "*" not in context.permissions and required not in context.permissions:
            raise PermissionError(f"缺少权限 {required}")

    def clear(self) -> None:
        self._cache.clear()

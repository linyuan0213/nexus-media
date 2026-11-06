"""元数据网关：统一上下文、缓存键和 singleflight 的入口边界。"""

from __future__ import annotations

import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any, Literal

import log
from app.domain.mediatypes import MediaType
from app.infrastructure.cache_system import get_cache_manager


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
        self._l2 = get_cache_manager().get_or_create(
            "metadata_gateway", cache_type="tiered", maxsize=1000, ttl=default_ttl
        )
        self._refreshing: set[str] = set()
        self._metrics: Counter[str] = Counter()

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
        if cached and cached[0] > time.monotonic() and cached[1].expires_at > datetime.now():
            self._metrics["l1_hit"] += 1
            return replace(cached[1], cache_hit=True)
        try:
            value = self._l2.get(key)
        except Exception:  # noqa: BLE001
            value = None
        if isinstance(value, MetadataEnvelope) and value.expires_at > datetime.now():
            self._metrics["l2_hit"] += 1
            self._cache[key] = (time.monotonic() + self._default_ttl * 4, value)
            return replace(value, cache_hit=True)
        self._metrics["miss"] += 1
        return None

    def _stale(self, key: str) -> MetadataEnvelope | None:
        cached = self._cache.get(key)
        if cached:
            self._metrics["stale"] += 1
            return replace(cached[1], cache_hit=True, stale=True, degraded=True)
        try:
            value = self._l2.get(key)
        except Exception:  # noqa: BLE001
            value = None
        if isinstance(value, MetadataEnvelope):
            self._metrics["stale"] += 1
            return replace(value, cache_hit=True, stale=True, degraded=True)
        return None

    def _remember(self, key: str, envelope: MetadataEnvelope, ttl: int) -> None:
        self._cache[key] = (time.monotonic() + max(ttl * 4, 60), envelope)
        try:
            self._l2.set(key, envelope, ttl=max(ttl * 4, 60))
        except Exception as exc:  # noqa: BLE001
            log.debug(f"[MetadataGateway]写入 L2 失败: {exc}")

    def metrics(self) -> dict[str, int]:
        return dict(self._metrics)

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
                stale = self._stale(key)
                if stale is not None:
                    self._refresh_async(
                        key,
                        provider,
                        external_id,
                        media_type=media_type,
                        context=ctx,
                        season=season,
                        scope=scope,
                        ttl=ttl or self._default_ttl,
                        with_episodes=with_episodes,
                    )
                    return stale
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
            self._remember(key, envelope, ttl or self._default_ttl)
            self._metrics["provider_call"] += 1
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
            self._remember(key, envelope, ttl or self._default_ttl)
            self._metrics["provider_call"] += 1
            return data

    def _refresh_async(
        self,
        key: str,
        provider: str,
        external_id: str,
        *,
        media_type: MediaType | None,
        context: MetadataContext,
        season: int,
        scope: str | None,
        ttl: int,
        with_episodes: bool,
    ) -> None:
        with self._guard:
            if key in self._refreshing:
                return
            self._refreshing.add(key)

        def refresh() -> None:
            try:
                with self._lock_for(key):
                    data = self._service.compose_for_ref(
                        provider,
                        external_id,
                        media_type=media_type or MediaType.UNKNOWN,
                        content_profile=context.content_profile,
                        allow_private=context.allow_private,
                        permissions=set(context.permissions),
                        user_id=context.user_id,
                        max_age_seconds=0,
                        with_episodes=with_episodes,
                    )
                    if isinstance(data, dict):
                        now = datetime.now()
                        identity_id, snapshot_id, _ = self._identity_fields(
                            provider, external_id, media_type=media_type, scope=self._scope(season, scope)
                        )
                        envelope = MetadataEnvelope(
                            provider=provider,
                            external_id=str(external_id),
                            media_type=media_type,
                            metadata=data,
                            fetched_at=now,
                            expires_at=now + timedelta(seconds=ttl),
                            identity_id=identity_id,
                            snapshot_id=snapshot_id,
                        )
                        self._remember(key, envelope, ttl)
                        self._metrics["provider_call"] += 1
                        self._metrics["refresh"] += 1
            except Exception:  # noqa: BLE001 - 后台刷新失败保留 stale
                self._metrics["refresh_failed"] += 1
            finally:
                with self._guard:
                    self._refreshing.discard(key)

        threading.Thread(target=refresh, daemon=True, name="metadata-refresh").start()

    def resolve_many(
        self,
        refs: list[tuple[str, str]],
        *,
        context: MetadataContext | None = None,
        media_type: MediaType | None = None,
        season: int = 0,
        scope: str | None = None,
    ) -> dict[tuple[str, str], MetadataEnvelope | None]:
        unique = list(dict.fromkeys(refs))
        if not unique:
            return {}
        with ThreadPoolExecutor(max_workers=min(4, len(unique)), thread_name_prefix="metadata-resolve") as pool:
            values = pool.map(
                lambda ref: self.resolve(
                    ref[0],
                    ref[1],
                    context=context,
                    media_type=media_type,
                    season=season,
                    scope=scope,
                ),
                unique,
            )
            return dict(zip(unique, values, strict=False))

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
        # 本地快照读取，不触发 provider；可见性由上层 API/任务授权负责。
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
        try:
            self._l2.clear()
        except Exception as exc:  # noqa: BLE001
            log.debug(f"[MetadataGateway]清理 L2 失败: {exc}")

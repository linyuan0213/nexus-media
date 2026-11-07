"""元数据网关：统一上下文、缓存键和 singleflight 的入口边界。"""

from __future__ import annotations

import copy
import hashlib
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any, Literal

import log
from app.domain.media_types import ProviderMediaType
from app.infrastructure.cache_system.metadata_cache import MetadataCache


@dataclass(frozen=True)
class MetadataContext:
    user_id: int | None = None
    # None 表示系统上下文/超级管理员，不受细粒度权限限制；
    # 普通用户始终使用显式权限集合，哪怕是空集合。
    permissions: frozenset[str] | None = None
    content_profile: str = "default"
    policy_key: str = "default"
    purpose: str = "api"
    allow_private: bool = False
    language: str = ""
    request_id: str = ""

    def permission_set(self) -> set[str] | None:
        return set(self.permissions) if self.permissions is not None else None

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
        is_superadmin = bool(getattr(user, "is_superadmin", False))
        user_permissions = frozenset(getattr(user, "permissions", ()) or ())
        permissions = None if is_superadmin else user_permissions
        if allow_private is None:
            allow_private = is_superadmin or "metadata:private:view" in user_permissions
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
    media_type: ProviderMediaType | None
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

    def __init__(self, service: Any, *, media_service: Any = None, default_ttl: int = 600):
        self._service = service
        self._media = media_service or getattr(service, "_media_service", None)
        self._default_ttl = default_ttl
        self._cache: dict[str, tuple[float, MetadataEnvelope]] = {}
        self._title_cache: dict[str, tuple[float, Any]] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()
        self._l2 = MetadataCache(prefix="gateway")
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
        media_type: ProviderMediaType | None,
        context: MetadataContext,
        scope: str,
        season: int,
    ) -> str:
        type_key = media_type.value if media_type else "auto"
        permission_key = "*" if context.permissions is None else ",".join(sorted(context.permissions))
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

    @staticmethod
    def _provider_ref(media_info: Any) -> tuple[str, str]:
        ref = str(getattr(media_info, "metadata_ref", "") or "").strip()
        if ":" in ref:
            provider, external_id = ref.split(":", 1)
            if provider and external_id and provider != "id":
                return provider.lower(), external_id
        provider = str(getattr(media_info, "anchor_provider", "") or "").strip().lower()
        external_id = str(getattr(media_info, "anchor_external_id", "") or "").strip()
        if provider and external_id:
            return provider, external_id
        for attr_name, key in (("tmdb_id", "tmdb"), ("douban_id", "douban"), ("bangumi_id", "bangumi")):
            value = str(getattr(media_info, attr_name, "") or "").strip()
            if value:
                return key, value
        return "", ""

    def _identity_fields(
        self,
        provider: str,
        external_id: str,
        *,
        media_type: ProviderMediaType | None,
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
        media_type: ProviderMediaType | None = None,
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
                    media_type=media_type or ProviderMediaType.UNKNOWN,
                    content_profile=ctx.content_profile,
                    allow_private=ctx.allow_private,
                    permissions=ctx.permission_set(),
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

    @staticmethod
    def _title_key(
        title: str,
        subtitle: str,
        media_type: ProviderMediaType | None,
        year: str | None,
        context: MetadataContext,
        strict: bool | None,
        language: str | None,
        chinese: bool,
        append_to_response: str | None,
    ) -> str:
        digest = hashlib.sha256(f"{title}\x00{subtitle}".encode()).hexdigest()[:24]
        permission_key = "*" if context.permissions is None else ",".join(sorted(context.permissions))
        type_key = media_type.value if media_type else "auto"
        return (
            f"title:{digest}:{type_key}:{year or ''}:{context.content_profile}:"
            f"{context.policy_key}:{context.language}:{context.allow_private}:{permission_key}:"
            f"{strict}:{language or ''}:{int(chinese)}:{append_to_response or ''}"
        )

    def resolve_by_title(
        self,
        title: str,
        *,
        subtitle: str | None = None,
        media_type: ProviderMediaType | None = None,
        year: str | None = None,
        context: MetadataContext | None = None,
        strict: bool | None = None,
        cache: bool = True,
        language: str | None = None,
        chinese: bool = True,
        append_to_response: str | None = None,
        ttl: int | None = None,
    ) -> Any | None:
        """按标题识别媒体；缓存键隔离画像、权限、类型与年份."""
        ctx = context or MetadataContext(purpose="identify")
        if self._media is None:
            self._metrics["title_unavailable"] += 1
            log.warn("[MetadataGateway]未注入 MediaService，标题识别不可用")
            return None
        safe_title = str(title or "")
        safe_subtitle = str(subtitle or "")
        key = self._title_key(
            safe_title,
            safe_subtitle,
            media_type,
            year,
            ctx,
            strict,
            language,
            chinese,
            append_to_response,
        )
        lock = self._lock_for(key)
        with lock:
            cached = self._title_cache.get(key)
            if cached is not None and cached[0] > time.monotonic():
                self._metrics["title_hit"] += 1
                return copy.deepcopy(cached[1])
            try:
                info = self._media.get_media_info(
                    title=safe_title,
                    subtitle=safe_subtitle or None,
                    mtype=media_type,
                    strict=strict,
                    cache=cache,
                    language=language,
                    chinese=chinese,
                    append_to_response=append_to_response,
                )
            except Exception:
                self._metrics["title_error"] += 1
                raise
            if info is not None:
                self._title_cache[key] = (
                    time.monotonic() + (ttl or self._default_ttl),
                    copy.deepcopy(info),
                )
                self._metrics["title_call"] += 1
            return info

    def lookup(
        self,
        provider: str,
        external_id: str,
        *,
        context: MetadataContext | None = None,
        media_type: ProviderMediaType | None = None,
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
                    permissions=ctx.permission_set(),
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
        media_type: ProviderMediaType | None,
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
                        media_type=media_type or ProviderMediaType.UNKNOWN,
                        content_profile=context.content_profile,
                        allow_private=context.allow_private,
                        permissions=context.permission_set(),
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
        media_type: ProviderMediaType | None = None,
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
        media_type: ProviderMediaType | None = None,
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
            permissions=ctx.permission_set(),
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
            permissions=ctx.permission_set(),
            **kwargs,
        )

    def episodes(
        self,
        provider: str,
        external_id: str,
        season: int = 1,
        *,
        context: MetadataContext | None = None,
        media_type: ProviderMediaType | None = None,
    ) -> list[dict[str, Any]]:
        ctx = context or MetadataContext()
        kwargs: dict[str, Any] = {
            "allow_private": ctx.allow_private,
            "permissions": sorted(ctx.permissions or ()),
        }
        return self._service.episodes(provider, str(external_id), season, **kwargs)

    def cached_details(
        self,
        provider: str,
        external_id: str | int | None,
        *,
        media_type: ProviderMediaType | str | None = None,
        extra: str = "",
        extras: tuple[str, ...] | None = None,
    ) -> Any | None:
        """读取 provider 本地缓存；所有 provider 共用同一缓存层."""
        lookup = getattr(self._service, "cached_details", None)
        if not callable(lookup):
            return None
        return lookup(
            provider,
            external_id,
            media_type=media_type,
            extra=extra,
            extras=extras,
        )

    def cached_details_for_media(self, media_info: Any, **kwargs: Any) -> Any | None:
        provider, external_id = self._provider_ref(media_info)
        if not provider or not external_id:
            return None
        return self.cached_details(provider, external_id, media_type=getattr(media_info, "type", None), **kwargs)

    def details(
        self,
        provider: str,
        external_id: str | int | None,
        *,
        media_type: ProviderMediaType | str | None = None,
        language: str | None = None,
        append_to_response: str | None = None,
        chinese: bool = True,
        context: MetadataContext | None = None,
    ) -> dict[str, Any]:
        """按 provider ref 获取详情；TMDB 兼容路径仅在网关内部处理."""
        provider_key = str(provider or "").strip().lower()
        if not provider_key or external_id in (None, ""):
            return {}
        if provider_key == "tmdb":
            return self._tmdb_info(
                mtype=media_type,
                tmdbid=external_id,
                language=language,
                append_to_response=append_to_response,
                chinese=chinese,
            )
        data = self.lookup(
            provider_key,
            str(external_id),
            context=context,
            media_type=ProviderMediaType.from_value(str(media_type)) if media_type else None,
        )
        return data or {}

    def details_for_media(self, media_info: Any, **kwargs: Any) -> dict[str, Any]:
        provider, external_id = self._provider_ref(media_info)
        if not provider or not external_id:
            return {}
        return self.details(provider, external_id, media_type=getattr(media_info, "type", None), **kwargs)

    def _tmdb_info(
        self,
        mtype: ProviderMediaType | str | None,
        tmdbid: str | int | None,
        *,
        language: str | None = None,
        append_to_response: str | None = None,
        chinese: bool = True,
    ) -> dict[str, Any]:
        """legacy 兼容读取：仅在网关内部委托 MediaService."""
        if self._media is None:
            self._metrics["legacy_unavailable"] += 1
            return {}
        return self._media.get_tmdb_info(
            mtype=mtype,
            tmdbid=tmdbid,
            language=language,
            append_to_response=append_to_response,
            chinese=chinese,
        )

    def media_info_on_files(
        self,
        file_list: list[str],
        *,
        tmdb_info: dict[str, Any] | None = None,
        media_type: ProviderMediaType | str | None = None,
        season: int | None = None,
        language: str | None = None,
        chinese: bool = True,
        append_to_response: str | None = None,
        backend: Any = None,
    ) -> Any:
        if self._media is None:
            self._metrics["legacy_unavailable"] += 1
            return {}
        return self._media.get_media_info_on_files(
            file_list=file_list,
            tmdb_info=tmdb_info,
            media_type=media_type,
            season=season,
            language=language,
            chinese=chinese,
            append_to_response=append_to_response,
            backend=backend,
        )

    def _tmdb_tv_seasons(self, tv_info: dict[str, Any] | None) -> list[dict[str, Any]]:
        if self._media is None:
            self._metrics["legacy_unavailable"] += 1
            return []
        return list(self._media.get_tmdb_tv_seasons(tv_info=tv_info) or [])

    def season_summaries(self, tv_info: dict[str, Any] | None) -> list[dict[str, Any]]:
        """返回季概要；TMDB 兼容字段由网关内部适配."""
        return self._tmdb_tv_seasons(tv_info)

    def _tmdb_season_detail(self, tmdbid: str | int | None, season: int) -> dict[str, Any]:
        if self._media is None:
            self._metrics["legacy_unavailable"] += 1
            return {}
        return self._media.get_tmdb_tv_season_detail(tmdbid=tmdbid, season=season) or {}

    def season_episodes(
        self,
        provider: str,
        external_id: str | int | None,
        season: int,
        *,
        media_type: ProviderMediaType | str | None = ProviderMediaType.SERIES,
        context: MetadataContext | None = None,
    ) -> dict[str, Any]:
        """按 provider ref 获取季详情；TMDB 走本地兼容实现."""
        if str(provider or "").strip().lower() == "tmdb":
            return self._tmdb_season_detail(external_id, season)
        episodes = self.episodes(
            str(provider),
            str(external_id),
            season,
            context=context,
            media_type=ProviderMediaType.from_value(str(media_type)) if media_type else ProviderMediaType.SERIES,
        )
        return {"episodes": episodes} if episodes else {}

    def genres(
        self,
        provider: str,
        external_id: str | int | None,
        *,
        media_type: ProviderMediaType | str | None = ProviderMediaType.SERIES,
        extras: tuple[str, ...] | None = None,
    ) -> set[str]:
        """读取缓存中的题材 ID，供订阅类型推断等只读判断使用."""
        info = self.cached_details(provider, external_id, media_type=media_type, extras=extras)
        if info is None:
            return set()
        raw = info.get("genres") if hasattr(info, "get") else getattr(info, "genres", None)
        result: set[str] = set()
        for genre in raw or []:
            genre_id = genre.get("id") if hasattr(genre, "get") else getattr(genre, "id", None)
            if genre_id:
                result.add(str(genre_id))
        return result

    def episode_images(
        self,
        tv_id: str | int | None,
        season_id: str | int | None,
        episode_id: str | int | None,
        original: bool = False,
    ) -> str:
        if self._media is None:
            self._metrics["legacy_unavailable"] += 1
            return ""
        return str(
            self._media.get_episode_images(
                tv_id=tv_id,
                season_id=season_id,
                episode_id=episode_id,
                orginal=original,
            )
            or ""
        )

    def directors_actors(self, tmdbinfo: dict[str, Any] | None) -> tuple[list[dict], list[dict]]:
        if self._media is None:
            self._metrics["legacy_unavailable"] += 1
            return [], []
        return self._media.get_tmdb_directors_actors(tmdbinfo=tmdbinfo)

    def all_names(self, provider: str, external_id: str | int | None, media_type: ProviderMediaType | str) -> list[str]:
        """媒体全部名称（正名/原名/别名/译名）."""
        if self._media is None or str(provider or "").lower() != "tmdb" or external_id in (None, ""):
            return []
        return list(self._media.get_all_names(int(external_id), ProviderMediaType.from_value(str(media_type))) or [])

    def person_aka_names(self, person_id: str | int | None) -> list[str]:
        """演职人员又名；仅网关内部委托 MediaService."""
        if self._media is None or not person_id:
            return []
        return list(self._media.get_tmdbperson_aka_names(person_id) or [])

    def search_page(
        self,
        query: str,
        *,
        provider: str | None = None,
        media_type: ProviderMediaType | str | None = None,
        year: str | None = None,
        page: int = 1,
        limit: int = 20,
        context: MetadataContext | None = None,
    ) -> list[dict[str, Any]]:
        """带分页的 provider 搜索；TMDB 兼容分页留在网关内部."""
        provider_key = str(provider or "").strip().lower()
        mtype = ProviderMediaType.from_value(str(media_type)) if media_type else None
        if provider_key == "tmdb":
            if self._media is None:
                return []
            return list(self._media.get_tmdb_infos(title=query, year=year, mtype=mtype, page=page) or [])
        return self.search(
            query=query,
            provider=provider_key or None,
            media_type=mtype,
            context=context,
            limit=limit,
        )

    def search_error(self) -> Any:
        """最近一次搜索错误；仅网关内部读取 provider 诊断信息."""
        if self._media is None:
            return None
        return self._media.get_tmdb_search_error()

    def season_summaries_by_id(self, external_id: str | int | None) -> list[dict[str, Any]]:
        """按 provider 引用获取季概要."""
        if self._media is None or external_id in (None, ""):
            return []
        return list(self._media.get_tmdb_tv_seasons_byid(tmdbid=external_id) or [])

    def person_credits(
        self,
        provider: str,
        external_id: str | int | None,
        *,
        media_type: ProviderMediaType | str | None = None,
    ) -> Any:
        """演职人员作品列表."""
        if str(provider or "").lower() != "tmdb" or self._media is None:
            return []
        mtype = ProviderMediaType.from_value(str(media_type)) if media_type else ProviderMediaType.MOVIE
        return self._media.get_tmdb_cats(tmdbid=external_id, mtype=mtype)

    def search_person(self, name: str) -> Any:
        """按姓名搜索演职人员."""
        if self._media is None:
            return []
        return self._media.search_tmdb_person(name=name)

    def related_items(
        self,
        kind: str,
        external_id: str | int | None,
        *,
        media_type: ProviderMediaType | str | None = None,
        page: int = 1,
        person_id: str | int | None = None,
    ) -> Any:
        """相似/推荐/人物作品；业务层只描述关系类型."""
        if self._media is None or (external_id in (None, "") and person_id in (None, "")):
            return []
        mtype = ProviderMediaType.from_value(str(media_type)) if media_type else ProviderMediaType.MOVIE
        is_movie = mtype == ProviderMediaType.MOVIE
        kind = str(kind or "").strip().lower()
        if kind == "similar":
            return (
                self._media.get_movie_similar(tmdbid=external_id, page=page)
                if is_movie
                else self._media.get_tv_similar(tmdbid=external_id, page=page)
            )
        if kind == "recommendations":
            return (
                self._media.get_movie_recommendations(tmdbid=external_id, page=page)
                if is_movie
                else self._media.get_tv_recommendations(tmdbid=external_id, page=page)
            )
        if kind == "person":
            return self._media.get_person_medias(personid=person_id, mtype=mtype, page=page)
        return []

    def detail_url(self, media_type: ProviderMediaType | str, external_id: str | int | None) -> str:
        """媒体详情页 URL；provider 兼容细节留在网关内部."""
        if self._media is None or external_id in (None, ""):
            return ""
        return str(self._media.get_detail_url(mtype=media_type, tmdbid=external_id) or "")

    def media_extras(self, media_info: Any) -> dict[str, Any]:
        """详情页扩展字段（背景、题材、花絮、演职员）."""
        if self._media is None or media_info is None:
            return {"background": [], "genres": [], "fact": "", "crews": [], "actors": []}
        mtype = getattr(media_info, "type", ProviderMediaType.MOVIE)
        provider_data = getattr(media_info, "provider_data", {}) or {}
        external_id = getattr(media_info, "tmdb_id", None)
        return {
            "background": self._media.get_tmdb_backdrops(tmdbinfo=provider_data),
            "genres": self._media.get_tmdb_genres_names(tmdbinfo=provider_data),
            "fact": self._media.get_tmdb_factinfo(media_info),
            "crews": self._media.get_tmdb_crews(tmdbinfo=provider_data, nums=6),
            "actors": self._media.get_tmdb_cats(mtype=mtype, tmdbid=external_id),
        }

    def episode_title(self, media_info: Any, language: str | None = None) -> str:
        """legacy 集标题补全；仅网关内部委托 MediaService."""
        if self._media is None:
            self._metrics["legacy_unavailable"] += 1
            return ""
        return str(self._media.get_episode_title(media_info, language=language) or "")

    def en_title(self, media_info: Any) -> str:
        if self._media is None:
            self._metrics["legacy_unavailable"] += 1
            return ""
        return str(self._media.get_tmdb_en_title(media_info) or "")

    def zhtw_title(self, media_info: Any) -> str:
        """legacy 繁体中文标题补全；仅网关内部委托 MediaService."""
        if self._media is None:
            self._metrics["legacy_unavailable"] += 1
            return ""
        return str(self._media.get_tmdb_zhtw_title(media_info) or "")

    def genre_catalog(self, media_type: ProviderMediaType | str) -> list[dict[str, Any]]:
        """类型目录；provider 兼容细节留在网关内部."""
        if self._media is None:
            return []
        mtype = ProviderMediaType.from_value(str(media_type))
        return list(self._media.get_tmdb_genres(mtype) or [])

    def discover_items(
        self,
        category: str,
        *,
        media_type: ProviderMediaType | str | None = None,
        page: int = 1,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """发现页数据；业务层只描述内容类别，不感知 provider 方法."""
        if self._media is None:
            return []
        mtype = ProviderMediaType.from_value(str(media_type)) if media_type else None
        category = str(category or "").strip().lower()
        if category == "hot_movies":
            return list(self._media.get_tmdb_hot_movies(page) or [])
        if category == "hot_tvs":
            return list(self._media.get_tmdb_hot_tvs(page) or [])
        if category == "new_movies":
            return list(self._media.get_tmdb_new_movies(page) or [])
        if category == "new_tvs":
            return list(self._media.get_tmdb_new_tvs(page) or [])
        if category == "trending":
            return list(self._media.get_tmdb_trending_all_week(page=page) or [])
        if category == "discover":
            return list(
                self._media.get_tmdb_discover(mtype=mtype or ProviderMediaType.MOVIE, page=page, params=params or {})
                or []
            )
        return []

    def provider_descriptor(self, provider_key: str | None) -> Any | None:
        if not provider_key:
            return None
        lookup = getattr(self._service, "provider_descriptor", None)
        if callable(lookup):
            return lookup(provider_key)
        return None

    def provider_display_name(self, provider_key: str | None) -> str:
        descriptor = self.provider_descriptor(provider_key)
        return str(getattr(descriptor, "display_name", "") or provider_key or "")

    def provider_is_virtual(self, provider_key: str | None) -> bool:
        descriptor = self.provider_descriptor(provider_key)
        return bool(getattr(descriptor, "virtual", False))

    def provider_rating_max(self, provider_key: str | None) -> int:
        descriptor = self.provider_descriptor(provider_key)
        return int(getattr(descriptor, "rating_max", 10) or 10)

    def provider_uniqueid_fallback(self, provider_key: str | None) -> str:
        descriptor = self.provider_descriptor(provider_key)
        return str(getattr(descriptor, "uniqueid_fallback", "") or "")

    def provider_detail_url(
        self,
        provider_key: str,
        external_id: str,
        media_type: ProviderMediaType | None = None,
    ) -> str:
        descriptor = self.provider_descriptor(provider_key)
        template = str(getattr(descriptor, "detail_url_template", "") or "")
        if not template:
            return ""
        type_value = "movie" if media_type == ProviderMediaType.MOVIE else "tv"
        return template.format(external_id=external_id, media_type=type_value)

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
        media_type: ProviderMediaType = ProviderMediaType.SERIES,
        season: int = 1,
        content_profile: str | None = None,
        provider_data: dict[str, Any] | None = None,
        prefer_detail: bool = False,
    ) -> int:
        ctx = context or MetadataContext(content_profile=content_profile or "default")
        if provider_data:
            if prefer_detail and str(external_id or "").isdigit():
                detail = self._tmdb_season_detail(external_id, season)
                episodes = detail.get("episodes") if isinstance(detail, dict) else None
                if isinstance(episodes, list) and episodes:
                    return len(episodes)
            if self._media is not None:
                count = self._media.get_tmdb_season_episodes_num(tv_info=provider_data, season=season)
                if int(count or 0) > 0:
                    return int(count)
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
                permissions=ctx.permission_set(),
            )
        )

    def similar_for_ref(
        self,
        provider: str,
        external_id: str,
        *,
        context: MetadataContext | None = None,
        media_type: ProviderMediaType = ProviderMediaType.MOVIE,
        title: str | None = None,
        content_profile: str = "default",
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        ctx = context or MetadataContext(content_profile=content_profile)
        return self._service.similar_for_ref(
            provider,
            str(external_id),
            media_type=media_type,
            title=title,
            content_profile=content_profile or ctx.content_profile,
            limit=limit,
            allow_private=ctx.allow_private,
            permissions=ctx.permission_set(),
        )

    def preview(
        self,
        refs: list[Any],
        *,
        context: MetadataContext | None = None,
        policy: str | None = None,
        anchor_provider: str | None = None,
        content_profile: str = "default",
        media_type: ProviderMediaType | None = None,
    ) -> Any:
        ctx = context or MetadataContext(content_profile=content_profile)
        return self._service.preview(
            refs,
            policy=policy,
            anchor_provider=anchor_provider,
            content_profile=content_profile or ctx.content_profile,
            media_type=media_type,
            allow_private=ctx.allow_private,
            permissions=ctx.permission_set(),
        )

    def link_subscription(self, media_info: Any, **kwargs: Any) -> Any:
        """订阅身份映射由网关委托内部服务，业务层不直接持有实现。"""
        return self._service.link_subscription(media_info, **kwargs)

    def person_detail(self, person_id: str) -> dict[str, Any] | None:
        return self._service.person_detail(person_id)

    def identity_detail(self, identity_id: str, *, allow_private: bool = False) -> dict[str, Any] | None:
        return self._service.identity_detail(identity_id, allow_private=allow_private)

    def pending_links(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return self._service.pending_links(limit=limit)

    def list_overrides(self, identity_id: str, *, user_id: int | None = None) -> list[dict[str, Any]]:
        return self._service.list_overrides(identity_id, user_id=user_id)

    def service_metrics(self) -> dict[str, Any]:
        return self._service.metrics()

    def bump_detail_cache_version(self) -> int:
        return int(self._service.bump_detail_cache_version())

    def _ensure_visible(self, media_info: Any, context: MetadataContext) -> None:
        provider = str(getattr(media_info, "anchor_provider", "") or "")
        if not provider:
            return
        descriptor = self.provider_descriptor(provider)
        if descriptor is None or getattr(descriptor, "visibility", "public") != "private":
            return
        if not context.allow_private:
            raise PermissionError(f"缺少私有元数据访问权限: {provider}")
        required = str(getattr(descriptor, "required_permission", "") or "metadata:private:view")
        if context.permissions is not None and "*" not in context.permissions and required not in context.permissions:
            raise PermissionError(f"缺少权限 {required}")

    def clear(self) -> None:
        self._cache.clear()
        self._title_cache.clear()
        try:
            self._l2.clear()
        except Exception as exc:  # noqa: BLE001
            log.debug(f"[MetadataGateway]清理 L2 失败: {exc}")

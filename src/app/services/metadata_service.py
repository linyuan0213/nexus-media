"""多源元数据业务服务（ADR-025）.

API 层只调用本服务；provider 注册、编排、快照持久化都在这里。
"""

from __future__ import annotations

import difflib
import re
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol

import log
from app.core.exceptions import ValidationError
from app.core.settings import settings
from app.db.repositories.media_identity_repository import MediaIdentityRepository
from app.db.repositories.person_identity_repository import PersonIdentityRepository
from app.domain.media_ref import MediaSubject
from app.domain.mediatypes import MediaType
from app.infrastructure.cache_system import get_cache_manager
from app.media.metadata import (
    DEFAULT_POLICY_KEY,
    FieldValue,
    MediaMetadata,
    MetadataOrchestrator,
    MetadataPolicy,
    ProviderCapability,
    ProviderRef,
    SearchQuery,
    resolve_policy,
)
from app.media.metadata.errors import ProviderError
from app.media.metadata.legacy import parse_legacy_ref
from app.media.metadata.metrics import record_degraded, record_event, record_snapshot
from app.media.metadata.metrics import snapshot as metrics_snapshot
from app.media.metadata.providers import register_builtin_providers
from app.media.metadata.registry import MetadataRegistry
from app.media.metadata.registry import registry as global_registry


class IdentityRepositoryProtocol(Protocol):
    def find_by_ref(self, provider: str, external_id: str, *, scope: str = "default") -> Any: ...

    def latest_snapshot(
        self,
        identity_id: str,
        *,
        policy_key: str | None = None,
        scope: str | None = None,
    ) -> Any: ...

    def get_overrides(self, identity_id: str, *, user_id: int | None = None) -> list[Any]: ...

    def set_parent(self, identity_id: str, parent_identity_id: str, season_number: int) -> bool: ...

    def upsert_override(
        self,
        identity_id: str,
        *,
        field_name: str,
        value: str,
        user_id: int | None = None,
        provider: str | None = None,
        external_id: str | None = None,
        locale: str | None = None,
        locked: bool = True,
    ) -> Any: ...

    def get_identity(self, identity_id: str) -> Any: ...

    def list_refs(self, identity_id: str) -> list[Any]: ...

    def list_pending_links(self, *, limit: int = 100) -> list[Any]: ...

    def review_link(
        self,
        identity_id: str,
        *,
        provider: str,
        external_id: str,
        approve: bool,
        confidence: float = 1.0,
        scope: str = "default",
    ) -> Any: ...

    def merge_identity(self, source_id: str, target_id: str) -> bool: ...

    def ensure_identity(
        self,
        *,
        identity_id: str | None = None,
        media_type: str = "unknown",
        content_profile: str = "default",
        title: str | None = None,
        year: str | None = None,
    ) -> Any: ...

    def upsert_ref(
        self,
        identity_id: str,
        *,
        provider: str,
        external_id: str,
        media_type: str | None = None,
        scope: str = "default",
        url: str | None = None,
        confidence: float = 1.0,
        link_method: str = "exact_ref",
        link_confidence: float = 1.0,
        reviewed: bool = False,
        is_primary: bool = False,
    ) -> Any: ...

    def save_snapshot(
        self,
        identity_id: str,
        *,
        policy_key: str,
        content_profile: str,
        snapshot_hash: str,
        payload: dict[str, Any],
        scope: str = "default",
        providers: list[str] | None = None,
        status: str = "ok",
    ) -> Any: ...


@dataclass(frozen=True)
class SubscriptionIdentityFields:
    identity_id: str | None = None
    anchor_provider: str | None = None
    anchor_external_id: str | None = None
    content_profile: str | None = None
    metadata_policy: str | None = None
    naming_profile: str | None = None

    def as_kwargs(self) -> dict[str, str | None]:
        return {
            "identity_id": self.identity_id,
            "anchor_provider": self.anchor_provider,
            "anchor_external_id": self.anchor_external_id,
            "content_profile": self.content_profile,
            "metadata_policy": self.metadata_policy,
            "naming_profile": self.naming_profile,
        }


@dataclass
class MetadataPreviewResult:
    metadata: MediaMetadata | None
    errors: list[ProviderError] = field(default_factory=list)

    @property
    def degraded(self) -> bool:
        return bool(self.errors)


class MetadataService:
    """元数据预览与快照保存."""

    def __init__(
        self,
        *,
        registry: MetadataRegistry | None = None,
        identity_repo: IdentityRepositoryProtocol | None = None,
        person_repo: PersonIdentityRepository | None = None,
        media_service: Any = None,
        system_default_policy: str | None = None,
        register_builtins: bool = True,
    ) -> None:
        self._registry = registry or global_registry
        self._orchestrator = MetadataOrchestrator(self._registry)
        self._identity_repo = identity_repo or MediaIdentityRepository()
        self._person_repo = person_repo or PersonIdentityRepository()
        self._media_service = media_service
        self._system_default_policy = system_default_policy
        self._builtin_lock = threading.Lock()
        self._builtin_ready = not register_builtins
        # 同一条目详情并发去重：详情页反复刷新时只允许一个浏览器抓取。
        self._inflight_lock = threading.Lock()
        self._inflight: dict[str, Future[Any]] = {}
        self._detail_cache = get_cache_manager().get_or_create(
            "metadata_detail", cache_type="tiered", maxsize=500, ttl=600
        )
        self._detail_version_lock = threading.Lock()
        self._anchor_cache: dict[tuple, tuple[float, str, str]] = {}
        self._anchor_locks: dict[tuple, threading.Lock] = {}
        self._anchor_locks_guard = threading.Lock()

    @property
    def system_default_policy(self) -> str:
        """优先使用显式注入值，否则读取当前系统配置。"""
        return self._system_default_policy or settings.media.metadata_default_policy or "tmdb_primary"

    def preview(
        self,
        refs: list[ProviderRef],
        *,
        policy: str | None = None,
        anchor_provider: str | None = None,
        content_profile: str = "default",
        media_type: MediaType | None = None,
        allow_private: bool = False,
        permissions: set[str] | None = None,
    ) -> MetadataPreviewResult:
        self._ensure_builtin()
        self._check_visibility(refs, allow_private=allow_private, permissions=permissions)
        try:
            resolved = resolve_policy(
                policy,
                anchor_provider=anchor_provider,
                system_default=self.system_default_policy,
            )
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        result = self._orchestrator.compose(
            identity_id="preview",
            refs=refs,
            policy=resolved,
            media_type=media_type,
            content_profile=content_profile,
        )
        if result.errors:
            record_degraded()
        return MetadataPreviewResult(metadata=result.metadata, errors=result.errors)

    def link_subscription(
        self,
        media_info: Any,
        *,
        media_type: MediaType,
        mediaid: str | None = None,
        content_profile: str | None = None,
        metadata_policy: str | None = None,
        naming_profile: str | None = None,
    ) -> SubscriptionIdentityFields:
        """把订阅的旧 ID 映射为 identity；失败不阻断订阅创建.

        mediaid 是用户实际点击的卡片引用，优先级高于 media_info.tmdb_id，
        保证「豆瓣卡片订阅」的 anchor 仍是豆瓣。
        """
        raw_id = mediaid or getattr(media_info, "tmdb_id", None)
        anchor = parse_legacy_ref(str(raw_id) if raw_id is not None else None, media_type)
        profile = (
            content_profile
            or str(getattr(media_info, "content_profile", "") or "")
            or ("anime" if media_type == MediaType.ANIME else "default")
        )
        fallback_provider = str(getattr(media_info, "anchor_provider", "") or "")
        fallback_external = str(getattr(media_info, "anchor_external_id", "") or "")
        if anchor is None and fallback_provider and fallback_external:
            anchor = ProviderRef(
                provider=fallback_provider,
                external_id=fallback_external,
                media_type=media_type,
            )
        if anchor is None:
            default_policy = metadata_policy or (
                f"provider_only:{profile}"
                if profile != "default" and self._registry.get_provider(profile) is not None
                else None
            )
            return SubscriptionIdentityFields(
                content_profile=profile,
                metadata_policy=default_policy,
                naming_profile=naming_profile,
            )

        refs = [anchor]
        matched = parse_legacy_ref(
            str(getattr(media_info, "tmdb_id", "") or ""),
            media_type,
        )
        season_num = 0
        if media_type in (MediaType.TV, MediaType.ANIME):
            season_num = int(getattr(media_info, "get_season_seq", lambda: 0)() or 0)
        if matched is not None and season_num and anchor.provider != "tmdb" and matched.provider == "tmdb":
            matched = matched.model_copy(update={"scope": f"season={season_num}"})
        if matched is not None and (matched.provider, matched.external_id, matched.scope) != (
            anchor.provider,
            anchor.external_id,
            anchor.scope,
        ):
            refs.append(matched)
        media_anchor_provider = str(getattr(media_info, "anchor_provider", "") or "")
        media_anchor_external = str(getattr(media_info, "anchor_external_id", "") or "")
        if (
            media_anchor_provider
            and media_anchor_external
            and all(
                (item.provider, item.external_id, item.scope)
                != (media_anchor_provider, media_anchor_external, "default")
                for item in refs
            )
        ):
            refs.append(
                ProviderRef(
                    provider=media_anchor_provider,
                    external_id=media_anchor_external,
                    media_type=media_type,
                    scope="default",
                )
            )

        try:
            matches = []
            for ref in refs:
                found = self._identity_repo.find_by_ref(ref.provider, ref.external_id, scope=ref.scope)
                if found is not None and all(item.IDENTITY_ID != found.IDENTITY_ID for item in matches):
                    matches.append(found)
            if matches:
                identity = matches[0]
                for other in matches[1:]:
                    self._identity_repo.merge_identity(other.IDENTITY_ID, identity.IDENTITY_ID)
            else:
                identity = self._identity_repo.ensure_identity(
                    media_type=media_type.value,
                    content_profile=profile,
                    title=getattr(media_info, "title", None),
                    year=getattr(media_info, "year", None),
                )
            for ref in refs:
                try:
                    self._identity_repo.upsert_ref(
                        identity.IDENTITY_ID,
                        provider=ref.provider,
                        external_id=ref.external_id,
                        media_type=media_type.value,
                        scope=ref.scope,
                        link_method="subscription",
                        link_confidence=1.0,
                        reviewed=True,
                        is_primary=ref is anchor,
                    )
                except ValueError as exc:
                    log.warn(f"[Metadata]订阅引用冲突，保留已有身份 {ref.provider}:{ref.external_id}: {exc}")
            self._link_parent_identity(
                identity,
                refs,
                media_type,
                season_num,
                getattr(media_info, "title", None),
                getattr(media_info, "year", None),
            )
            if metadata_policy:
                policy_key = metadata_policy
            elif profile != "default" and self._registry.get_provider(profile) is not None:
                policy_key = f"provider_only:{profile}"
            else:
                policy_key = resolve_policy(
                    None,
                    anchor_provider=anchor.provider,
                    system_default=self.system_default_policy,
                ).key
            return SubscriptionIdentityFields(
                identity_id=identity.IDENTITY_ID,
                anchor_provider=anchor.provider,
                anchor_external_id=anchor.external_id,
                content_profile=profile,
                metadata_policy=policy_key,
                naming_profile=naming_profile,
            )
        except Exception as exc:  # noqa: BLE001 - 双写失败不阻断旧订阅创建
            log.warn(f"[Metadata]订阅身份双写失败 {anchor.provider}:{anchor.external_id}: {exc}")
            return SubscriptionIdentityFields(
                anchor_provider=anchor.provider,
                anchor_external_id=anchor.external_id,
                content_profile=profile,
                metadata_policy=metadata_policy,
                naming_profile=naming_profile,
            )

    def hydrate_media(self, media_info: Any) -> bool:
        """按已有锚点补齐 media_info 图片，不直接依赖任何具体 provider."""
        refs: list[tuple[str, str]] = []
        anchor = str(getattr(media_info, "anchor_provider", "") or "")
        anchor_id = str(getattr(media_info, "anchor_external_id", "") or "")
        if anchor and anchor_id:
            refs.append((anchor, anchor_id))
        douban_id = str(getattr(media_info, "douban_id", "") or "")
        if douban_id:
            refs.append(("douban", douban_id))
        tmdb_id = str(getattr(media_info, "tmdb_id", "") or "")
        if tmdb_id.isdigit():
            refs.append(("tmdb", tmdb_id))
        seen: set[tuple[str, str]] = set()
        for provider, external_id in refs:
            if (provider, external_id) in seen:
                continue
            seen.add((provider, external_id))
            try:
                record = self.lookup(
                    provider=provider,
                    external_id=external_id,
                    media_type=getattr(media_info, "type", None),
                    scope=str(getattr(media_info, "content_profile", "") or "default"),
                    content_profile=str(getattr(media_info, "content_profile", "") or ""),
                    allow_private=True,
                )
            except Exception:  # noqa: BLE001
                continue
            images = record.get("images") if isinstance(record, dict) else getattr(record, "images", {})
            images = images or {}
            poster = images.get("poster") or []
            if poster:
                asset = poster[0]
                media_info.poster_path = asset.get("url") if isinstance(asset, dict) else getattr(asset, "url", None)
                fanart = images.get("fanart") or []
                if fanart:
                    first = fanart[0]
                    media_info.fanart_backdrop = (
                        first.get("url") if isinstance(first, dict) else getattr(first, "url", None)
                    )
                return True
        return False

    def identify_anchor(
        self,
        media_info: Any,
        *,
        policy: str | None = None,
        media_type: MediaType | None = None,
    ) -> bool:
        """按系统策略为普通媒体选择主源锚点，失败时按回退链尝试。

        返回 True 表示找到了新的主源并写入 media_info.anchor_*。
        """
        profile = str(getattr(media_info, "content_profile", "") or "default")
        if profile != "default":
            return False
        policy_key = str(policy or settings.media.metadata_default_policy or "tmdb_primary")
        candidates = sorted(
            self._registry.list_providers(
                capability=ProviderCapability.SEARCH,
                visibility="public",
            ),
            key=lambda item: int(getattr(item.descriptor, "subscription_order", 100)),
        )
        if not candidates:
            return False
        primary = policy_key.split("_", 1)[0]
        if not any(item.descriptor.provider_key == primary for item in candidates):
            primary = candidates[0].descriptor.provider_key
        anchor_provider = str(getattr(media_info, "anchor_provider", "") or "")
        if not anchor_provider and getattr(media_info, f"{primary}_id", None):
            return False
        order = [
            primary,
            *[item.descriptor.provider_key for item in candidates if item.descriptor.provider_key != primary],
        ]
        title = str(
            getattr(media_info, "title", "")
            or getattr(media_info, "get_title_string", lambda: "")()
            or getattr(media_info, "org_string", "")
            or ""
        ).strip()
        if not title:
            return False
        target_type = media_type or getattr(media_info, "type", None) or MediaType.MOVIE
        cache_key = (policy_key, title.casefold(), str(getattr(media_info, "year", "") or ""), target_type.value)
        cached = self._anchor_cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < 300:
            _, cached_provider, cached_external = cached
            media_info.anchor_provider = cached_provider
            media_info.anchor_external_id = cached_external
            if cached_provider == "bangumi":
                media_info.type = MediaType.ANIME
                media_info.content_profile = "anime"
            return True
        with self._anchor_locks_guard:
            anchor_lock = self._anchor_locks.setdefault(cache_key, threading.Lock())
        with anchor_lock:
            # 双检：等待同一标题的其他线程完成搜索后直接复用缓存。
            cached = self._anchor_cache.get(cache_key)
            if cached and time.monotonic() - cached[0] < 300:
                _, cached_provider, cached_external = cached
                media_info.anchor_provider = cached_provider
                media_info.anchor_external_id = cached_external
                if cached_provider == "bangumi":
                    media_info.type = MediaType.ANIME
                    media_info.content_profile = "anime"
                return True
            return self._identify_anchor_search(
                media_info,
                policy_key=policy_key,
                title=title,
                target_type=target_type,
                order=order,
                cache_key=cache_key,
            )

    def _identify_anchor_search(
        self,
        media_info: Any,
        *,
        policy_key: str,
        title: str,
        target_type: MediaType,
        order: list[str],
        cache_key: tuple,
    ) -> bool:
        for provider in order:
            provider_obj = self._registry.get_provider(provider)
            descriptor = getattr(provider_obj, "descriptor", None)
            content_profile = str(getattr(descriptor, "default_content_profile", "") or "default")
            try:
                hits = self.search(
                    query=title,
                    provider=provider,
                    media_type=target_type,
                    content_profile=content_profile,
                    limit=5,
                )
            except Exception as exc:  # noqa: BLE001
                log.debug(f"[Metadata]主源识别失败 {provider}: {exc}")
                continue
            if not hits:
                continue
            year = str(getattr(media_info, "year", "") or "")
            normalized = re.sub(r"[\W_]+", "", title.casefold())

            def _score(item: dict) -> float:
                candidate = re.sub(
                    r"[\W_]+",
                    "",
                    str(item.get("title") or item.get("name") or "").casefold(),
                )
                score = difflib.SequenceMatcher(None, normalized, candidate).ratio() if normalized else 0.0
                item_year = str(item.get("year") or "")
                if year and item_year:
                    score += 0.25 if year == item_year else -0.15
                return score

            ranked = sorted(hits, key=_score, reverse=True)
            hit = ranked[0]
            if _score(hit) < 0.55:
                log.debug(f"[Metadata]主源 {provider} 标题匹配度过低: {hit.get('title')}")
                continue
            ref = hit.get("ref") or {}
            external_id = str(ref.get("external_id") or "")
            if not external_id:
                continue
            media_info.anchor_provider = provider
            media_info.anchor_external_id = external_id
            self._anchor_cache[cache_key] = (time.monotonic(), provider, external_id)
            if content_profile == "anime":
                media_info.type = MediaType.ANIME
                media_info.content_profile = content_profile
            log.info(f"[Metadata]主源策略 {policy_key} 命中 {provider}:{external_id}")
            return True
        return False

        return False

    def compose_for_media(
        self,
        media_info: Any,
        *,
        policy: str | None = None,
        anchor_provider: str | None = None,
        content_profile: str | None = None,
        with_episodes: bool = False,
        persist: bool = False,
        max_age_seconds: int = 0,
        locked: dict[str, FieldValue] | None = None,
        user_id: int | None = None,
        refs_override: list[ProviderRef] | None = None,
    ) -> MediaMetadata | None:
        """为现有 MediaInfo 构建快照（无 TMDB 场景的刮削入口）.

        with_episodes=True 时按需展开分集（豆瓣 HTML 较慢，仅供刮削后台调用）。
        """
        self._ensure_builtin()
        media_type = getattr(media_info, "type", None) or MediaType.UNKNOWN
        anchor_provider = anchor_provider or str(getattr(media_info, "anchor_provider", "") or "")
        anchor_external = str(getattr(media_info, "anchor_external_id", "") or "")
        ref = parse_legacy_ref(str(getattr(media_info, "tmdb_id", "") or ""), media_type)
        refs = []
        season = None
        if media_type in {MediaType.TV, MediaType.ANIME}:
            try:
                season = int(getattr(media_info, "get_season_seq", lambda: 0)() or 0) or None
            except (TypeError, ValueError):
                season = None
        if ref is not None:
            if season:
                ref = ref.model_copy(update={"scope": f"season={season}"})
            refs.append(ref)
        if (
            anchor_provider
            and anchor_external
            and all((item.provider, item.external_id) != (anchor_provider, anchor_external) for item in refs)
        ):
            refs.append(
                ProviderRef(
                    provider=anchor_provider,
                    external_id=anchor_external,
                    media_type=media_type,
                )
            )
        legacy_ref = media_info.get_media_ref() if hasattr(media_info, "get_media_ref") else None
        if legacy_ref is not None and all(
            (item.provider, item.external_id) != (legacy_ref.provider, legacy_ref.external_id) for item in refs
        ):
            refs.append(
                ProviderRef(
                    provider=legacy_ref.provider,
                    external_id=legacy_ref.external_id,
                    media_type=media_type,
                )
            )
        if anchor_provider:
            for index, item in enumerate(refs):
                if item.provider == anchor_provider:
                    refs.insert(0, refs.pop(index))
                    break
        if refs_override is not None:
            refs = list(refs_override)
        media_profile = getattr(media_info, "content_profile", "default") or "default"
        anchor_external = getattr(media_info, "anchor_external_id", None)
        if (
            refs_override is None
            and media_profile != "default"
            and anchor_external
            and self._registry.get_provider(media_profile) is not None
        ):
            refs = [
                ProviderRef(
                    provider=media_profile,
                    external_id=str(anchor_external),
                    media_type=media_type,
                )
            ]
        if not refs:
            return None

        anchor = anchor_provider or refs[0].provider
        effective_policy = policy
        if refs_override and media_profile != "default":
            effective_policy = f"provider_only:{refs[0].provider}"
        elif (
            refs_override is None
            and media_profile != "default"
            and self._registry.get_provider(media_profile) is not None
            and effective_policy in (None, "", self.system_default_policy, DEFAULT_POLICY_KEY)
        ):
            # 旧自定义画像订阅可能仍存着系统默认 tmdb_primary；必须回到自身 provider
            effective_policy = f"provider_only:{media_profile}"
        try:
            if refs[0].provider == media_profile and media_profile != "default":
                resolved = resolve_policy(
                    effective_policy or f"provider_only:{media_profile}",
                    anchor_provider=anchor,
                    system_default=self.system_default_policy,
                )
            else:
                resolved = resolve_policy(
                    effective_policy,
                    anchor_provider=anchor,
                    system_default=self.system_default_policy,
                )
        except ValueError:
            resolved = self.get_policy(None, anchor_provider=anchor)
        profile = content_profile or media_profile or ("anime" if media_type == MediaType.ANIME else "default")
        identity = self._resolve_identity(media_info, refs, media_type, profile, persist=persist)
        identity_id = identity.IDENTITY_ID if identity is not None else "preview"

        snapshot_scope = f"season={season}" if season else "default"
        if identity is not None and max_age_seconds > 0 and user_id is None:
            cached = self._identity_repo.latest_snapshot(identity_id, policy_key=resolved.key, scope=snapshot_scope)
            if cached is not None and datetime.now() - cached.CREATED_AT <= timedelta(seconds=max_age_seconds):
                try:
                    cached_metadata = MediaMetadata.model_validate_json(cached.PAYLOAD)
                    # 旧版本可能落库了没有标题/图片的空快照，不能继续复用。
                    cached_ok = bool(cached_metadata.fields.get("title"))
                    if cached_ok and not cached_metadata.images:
                        cached_ok = not self._refs_support_images(refs)
                    if (
                        cached_ok
                        and media_type in {MediaType.MOVIE, MediaType.TV, MediaType.ANIME}
                        and self._refs_support_images(refs)
                        and not (cached_metadata.images or {}).get("poster")
                    ):
                        # 只有 fanart/截图时仍视为不完整：海报是媒体库卡片的核心图。
                        cached_ok = False
                    if cached_ok:
                        self._attach_source_hints(cached_metadata, media_info)
                        return cached_metadata
                    log.debug("[Metadata]旧快照缺少标题/图片，重新合成")
                except Exception as exc:  # noqa: BLE001 - 旧快照结构不兼容时重新合成
                    log.debug(f"[Metadata]忽略旧快照: {exc}")

        if locked is None and identity is not None:
            locked = self._load_locked_fields(identity_id, user_id=user_id)

        result = self._orchestrator.compose(
            identity_id=identity_id,
            refs=refs,
            policy=resolved,
            media_type=media_type,
            content_profile=profile,
            scope=snapshot_scope,
            locked=locked,
        )
        metadata = result.metadata
        if metadata is not None:
            self._attach_source_hints(metadata, media_info)
        if with_episodes and metadata is not None and media_type in {MediaType.TV, MediaType.ANIME}:
            target_seasons = [season] if season else [item.season_number for item in metadata.seasons] or [1]
            for target_season in target_seasons:
                if any(item.season_number == target_season for item in metadata.episodes):
                    continue
                for ref in sorted(refs, key=lambda item: self._source_tier_rank(item.provider)):
                    provider = self._registry.get_provider(ref.provider)
                    if provider is None:
                        continue
                    try:
                        episodes = provider.episodes(ref, target_season, None)
                    except Exception as exc:  # noqa: BLE001 - 分集失败不阻断刮削
                        log.warn(f"[Metadata]分集展开失败 {ref.provider}:{ref.external_id}: {exc}")
                        continue
                    if episodes:
                        metadata.episodes.extend(episodes)
                        break
        if persist and identity is not None and metadata is not None and user_id is None:
            try:
                self._persist_snapshot(identity, metadata, resolved.key, refs, scope=snapshot_scope)
            except Exception as exc:  # noqa: BLE001
                log.warn(f"[Metadata]快照落库失败 {identity.IDENTITY_ID}: {exc}")
        if result.errors:
            record_degraded()
        return metadata

    @staticmethod
    def _attach_source_hints(metadata: MediaMetadata, media_info: Any) -> None:
        """把下载站点携带的标签/描述送入快照，供插件判断版本性质。"""
        labels = getattr(media_info, "labels", None)
        if isinstance(labels, str):
            labels = [item for item in labels.replace("，", ",").replace("|", ",").split(",") if item.strip()]
        if isinstance(labels, (list, tuple, set)):
            values = [str(item).strip() for item in labels if str(item).strip()]
            if values:
                metadata.extra["source.labels"] = values
        description = getattr(media_info, "description", None) or getattr(media_info, "org_string", None)
        if description:
            metadata.extra["source.description"] = str(description)

    def _refs_support_images(self, refs: list[ProviderRef]) -> bool:
        """判断引用中的 provider 是否本应提供图片，用于识别旧空快照."""
        for ref in refs:
            provider = self._registry.get_provider(ref.provider)
            if provider is not None and ProviderCapability.IMAGES in provider.descriptor.capabilities:
                return True
        return False

    def _resolve_identity(
        self,
        media_info: Any,
        refs: list[ProviderRef],
        media_type: MediaType,
        profile: str,
        *,
        persist: bool,
    ):
        anchor = refs[0]
        identity = self._identity_repo.find_by_ref(anchor.provider, anchor.external_id, scope=anchor.scope)
        if identity is None and persist:
            identity = self._identity_repo.ensure_identity(
                media_type=media_type.value,
                content_profile=profile,
                title=getattr(media_info, "title", None),
                year=getattr(media_info, "year", None),
            )
        if identity is None:
            return None
        for ref in refs:
            self._identity_repo.upsert_ref(
                identity.IDENTITY_ID,
                provider=ref.provider,
                external_id=ref.external_id,
                media_type=media_type.value,
                scope=ref.scope,
                link_method="scrape",
                link_confidence=1.0,
                reviewed=False,
                is_primary=ref is anchor,
            )
        return identity

    def _source_tier_rank(self, provider_key: str) -> int:
        provider = self._registry.get_provider(provider_key)
        if provider is None:
            return 99
        order = {"api": 0, "html": 1, "scraping": 2}
        tiers = provider.descriptor.source_tiers or ()
        return min((order.get(str(tier), 99) for tier in tiers), default=99)

    def _link_parent_identity(
        self,
        identity: Any,
        refs: list[ProviderRef],
        media_type: MediaType,
        season: int,
        title: str | None,
        year: str | None,
    ) -> None:
        if media_type not in {MediaType.TV, MediaType.ANIME} or season <= 0:
            return
        tmdb_ref = next(
            (ref for ref in refs if ref.provider == "tmdb" and str(ref.external_id).isdigit()),
            None,
        )
        if tmdb_ref is None:
            return
        parent = self._identity_repo.find_by_ref("tmdb", tmdb_ref.external_id, scope="default")
        if parent is None:
            parent = self._identity_repo.ensure_identity(
                media_type=media_type.value,
                content_profile=getattr(identity, "CONTENT_PROFILE", "default"),
                title=title,
                year=year,
            )
            self._identity_repo.upsert_ref(
                parent.IDENTITY_ID,
                provider="tmdb",
                external_id=tmdb_ref.external_id,
                media_type=media_type.value,
                scope="default",
                link_method="parent",
                link_confidence=1.0,
                reviewed=True,
                is_primary=True,
            )
        if parent.IDENTITY_ID != identity.IDENTITY_ID:
            self._identity_repo.set_parent(identity.IDENTITY_ID, parent.IDENTITY_ID, season)

    def _load_locked_fields(self, identity_id: str, *, user_id: int | None = None) -> dict[str, FieldValue]:
        locked: dict[str, FieldValue] = {}
        rows = list(self._identity_repo.get_overrides(identity_id, user_id=None))
        if user_id is not None:
            rows.extend(self._identity_repo.get_overrides(identity_id, user_id=user_id))
        for row in rows:
            if not row.LOCKED:
                continue
            locked[row.FIELD_NAME] = FieldValue(
                value=row.VALUE,
                provider=row.PROVIDER or "manual",
                external_id=row.EXTERNAL_ID or "",
                locale=row.LOCALE,
                locked=True,
            )
        return locked

    def _persist_snapshot(
        self,
        identity,
        metadata: MediaMetadata,
        policy_key: str,
        refs: list[ProviderRef],
        *,
        scope: str = "default",
    ) -> None:
        latest = self._identity_repo.latest_snapshot(identity.IDENTITY_ID, policy_key=policy_key, scope=scope)
        if latest is not None and latest.SNAPSHOT_HASH == metadata.snapshot_hash:
            return
        self._link_person_credits(metadata)
        conflicts = len(metadata.extra.get("conflicts") or [])
        record_snapshot(conflicts=conflicts)
        record_event("metadata.snapshot.created", identity_id=identity.IDENTITY_ID, conflicts=conflicts)
        self._identity_repo.save_snapshot(
            identity.IDENTITY_ID,
            policy_key=policy_key,
            content_profile=metadata.content_profile,
            scope=scope,
            snapshot_hash=metadata.snapshot_hash,
            payload=metadata.model_dump(mode="json"),
            providers=sorted({ref.provider for ref in refs}),
        )

    def _link_person_credits(self, metadata: MediaMetadata) -> None:
        """把 provider credits 写入人员实体；失败不影响作品快照."""
        if self._person_repo is None:
            return
        for credit in metadata.credits:
            provider = str(credit.provider or "").strip()
            external_id = str(credit.external_id or "").strip()
            if not provider or not external_id or not credit.name:
                continue
            try:
                person = self._person_repo.find_by_ref(provider, external_id)
                if person is None:
                    person = self._person_repo.ensure_person(
                        name=credit.name,
                        images=[credit.image_url] if credit.image_url else [],
                    )
                    self._person_repo.upsert_ref(
                        person.PERSON_ID,
                        provider=provider,
                        external_id=external_id,
                    )
                credit.person_id = person.PERSON_ID
            except Exception as exc:  # noqa: BLE001 - 人员失败不阻断作品
                log.debug(f"[Metadata]人员身份写入失败 {provider}:{external_id}: {exc}")

    def list_overrides(self, identity_id: str, *, user_id: int | None = None) -> list[dict[str, Any]]:
        rows = list(self._identity_repo.get_overrides(identity_id, user_id=None))
        if user_id is not None:
            rows.extend(self._identity_repo.get_overrides(identity_id, user_id=user_id))
        return [row.as_dict() for row in rows]

    def set_override(
        self,
        identity_id: str,
        *,
        field_name: str,
        value: str,
        user_id: int | None = None,
        locked: bool = True,
    ) -> dict[str, Any]:
        row = self._identity_repo.upsert_override(
            identity_id,
            field_name=field_name,
            value=value,
            user_id=user_id,
            locked=locked,
        )
        return row.as_dict()

    def merge_identity(self, source_id: str, target_id: str) -> bool:
        return self._identity_repo.merge_identity(source_id, target_id)

    def person_detail(self, person_id: str) -> dict[str, Any] | None:
        person = self._person_repo.get_person(person_id)
        if person is None:
            return None
        data = self._person_repo.decode_person(person)
        refs = self._person_repo.get_refs(person_id)
        data["refs"] = [ref.as_dict() for ref in refs]
        tmdb_ref = next((ref for ref in refs if ref.PROVIDER == "tmdb"), None)
        if tmdb_ref is not None and self._media_service is not None:
            try:
                data["works"] = self._media_service.get_person_medias(tmdb_ref.EXTERNAL_ID)
            except Exception as exc:  # noqa: BLE001 - 作品聚合失败不影响人员详情
                log.debug(f"[Metadata]人员作品获取失败 {person_id}: {exc}")
                data["works"] = []
        else:
            data["works"] = []
        return data

    def pending_links(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return [
            {
                "identity_id": ref.IDENTITY_ID,
                "provider": ref.PROVIDER,
                "external_id": ref.EXTERNAL_ID,
                "link_method": ref.LINK_METHOD,
                "link_confidence": ref.LINK_CONFIDENCE,
                "reviewed": bool(ref.REVIEWED),
            }
            for ref in self._identity_repo.list_pending_links(limit=limit)
        ]

    def review_link(
        self,
        identity_id: str,
        *,
        provider: str,
        external_id: str,
        approve: bool,
        confidence: float = 1.0,
        scope: str = "default",
    ) -> dict[str, Any] | None:
        ref = self._identity_repo.review_link(
            identity_id,
            provider=provider,
            external_id=external_id,
            approve=approve,
            confidence=confidence,
            scope=scope,
        )
        if ref is None:
            return None
        return {"provider": ref.PROVIDER, "external_id": ref.EXTERNAL_ID, "reviewed": bool(ref.REVIEWED)}

    def identity_detail(
        self,
        identity_id: str,
        *,
        allow_private: bool = False,
    ) -> dict[str, Any] | None:
        identity = self._identity_repo.get_identity(identity_id)
        if identity is None:
            return None
        if identity.CONTENT_PROFILE not in ("", "default") and not allow_private:
            return None
        refs = self._identity_repo.list_refs(identity_id)
        snapshot = self._identity_repo.latest_snapshot(identity_id)
        conflicts: list[Any] = []
        if snapshot is not None:
            try:
                metadata = MediaMetadata.model_validate_json(snapshot.PAYLOAD)
                conflicts = metadata.extra.get("conflicts") or []
            except Exception:  # noqa: BLE001
                conflicts = []
        return {
            "identity": identity.as_dict(),
            "refs": [ref.as_dict() for ref in refs],
            "latest_snapshot": {
                "policy_key": snapshot.POLICY_KEY,
                "snapshot_hash": snapshot.SNAPSHOT_HASH,
                "created_at": snapshot.CREATED_AT.isoformat(),
            }
            if snapshot is not None
            else None,
            "conflicts": conflicts,
        }

    def latest_snapshot_for_media(self, media_info: Any) -> MediaMetadata | None:
        """只读快照，供重命名/整理消费；不发起网络请求."""
        media_type = getattr(media_info, "type", None) or MediaType.UNKNOWN
        anchor_provider = str(getattr(media_info, "anchor_provider", "") or "")
        anchor_external = str(getattr(media_info, "anchor_external_id", "") or "")
        ref = None
        if anchor_provider and anchor_external:
            ref = ProviderRef(
                provider=anchor_provider,
                external_id=anchor_external,
                media_type=media_type,
            )
        if ref is None:
            ref = parse_legacy_ref(str(getattr(media_info, "tmdb_id", "") or ""), media_type)
        if ref is None:
            return None
        identity = self._identity_repo.find_by_ref(ref.provider, ref.external_id, scope=ref.scope)
        if identity is None:
            profile = str(getattr(media_info, "content_profile", "") or "")
            if profile and profile != "default":
                identity = self._identity_repo.find_by_ref(profile, ref.external_id)
        if identity is None:
            return None
        scope = "default"
        if media_type in {MediaType.TV, MediaType.ANIME}:
            try:
                season = int(getattr(media_info, "get_season_seq", lambda: 0)() or 0)
            except (TypeError, ValueError):
                season = 0
            if season:
                scope = f"season={season}"
        snapshot = self._identity_repo.latest_snapshot(identity.IDENTITY_ID, scope=scope)
        if snapshot is None:
            return None
        try:
            return MediaMetadata.model_validate_json(snapshot.PAYLOAD)
        except Exception as exc:  # noqa: BLE001 - 旧快照不兼容时回退旧路径
            log.debug(f"[Metadata]读取快照失败: {exc}")
            return None

    def search(
        self,
        *,
        query: str,
        provider: str | None = None,
        media_type: MediaType | None = None,
        content_profile: str = "default",
        limit: int = 20,
        allow_private: bool = False,
        permissions: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        self._ensure_builtin()
        if not query.strip():
            return []
        providers = self._registry.list_providers(capability=ProviderCapability.SEARCH)
        if provider:
            providers = [item for item in providers if item.descriptor.provider_key == provider]
        hits = []
        for item in providers:
            descriptor = item.descriptor
            if descriptor.visibility == "private":
                required = descriptor.required_permission or "metadata:private:view"
                if not allow_private or (
                    permissions is not None and "*" not in permissions and required not in permissions
                ):
                    continue
            runtime = self._orchestrator.runtime_for(descriptor)
            try:
                runtime.acquire()
                results = item.search(
                    SearchQuery(
                        query=query,
                        media_type=media_type,
                        content_profile=content_profile,
                        limit=limit,
                    ),
                    None,
                )
            except ProviderError as exc:
                runtime.record_failure()
                log.warn(f"[Metadata]搜索失败 {descriptor.provider_key}: {exc}")
                continue
            except Exception as exc:  # noqa: BLE001 - 单源搜索失败不影响其他源
                runtime.record_failure()
                log.warn(f"[Metadata]搜索失败 {descriptor.provider_key}: {exc}")
                continue
            runtime.record_success()
            for hit in results or []:
                hits.append(hit.model_dump(mode="json"))
        hits.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
        return hits[:limit]

    def compose_for_ref(
        self,
        provider: str,
        external_id: str,
        *,
        media_type: MediaType = MediaType.UNKNOWN,
        content_profile: str = "default",
        include_tmdb: bool = True,
        max_age_seconds: int = 300,
        user_id: int | None = None,
        refs: list[ProviderRef] | None = None,
        allow_private: bool = False,
        permissions: set[str] | None = None,
    ) -> dict[str, Any] | None:
        """按外部锚点合成快照；显式 refs 时保留聚合来源上下文."""
        if refs:
            self._check_visibility(refs, allow_private=allow_private, permissions=permissions)
        identity = self._identity_repo.find_by_ref(provider, str(external_id))
        tmdb_id = ""
        season = 0
        if identity is not None:
            for ref in self._identity_repo.list_refs(identity.IDENTITY_ID):
                if ref.PROVIDER == "tmdb" and str(ref.EXTERNAL_ID or "").isdigit():
                    if include_tmdb:
                        tmdb_id = str(ref.EXTERNAL_ID)
                    if ref.SCOPE.startswith("season="):
                        try:
                            season = int(ref.SCOPE.split("=", 1)[1])
                        except ValueError:
                            season = 0
                    if include_tmdb or season:
                        break
        scope = f"season={season}" if season else "default"
        if not refs and identity is not None and max_age_seconds > 0 and user_id is None:
            cached = self._identity_repo.latest_snapshot(identity.IDENTITY_ID, scope=scope)
            if cached is not None and datetime.now() - cached.CREATED_AT <= timedelta(seconds=max_age_seconds):
                try:
                    return MediaMetadata.model_validate_json(cached.PAYLOAD).model_dump(mode="json")
                except Exception as exc:  # noqa: BLE001
                    log.debug(f"[Metadata]忽略详情旧快照: {exc}")

        media_info = MediaSubject(
            media_type=media_type,
            tmdb_id=tmdb_id,
            content_profile=content_profile,
            anchor_provider=provider,
            anchor_external_id=str(external_id),
            begin_season=season or None,
        )
        snapshot = self.compose_for_media(
            media_info,
            content_profile=content_profile,
            with_episodes=True,
            user_id=user_id,
            refs_override=refs,
        )
        if snapshot is None:
            return None
        data = snapshot.model_dump(mode="json")
        data.setdefault("extra", {})["douban.season"] = season
        return data

    def similar_for_ref(
        self,
        provider: str,
        external_id: str,
        *,
        media_type: MediaType = MediaType.MOVIE,
        title: str | None = None,
        content_profile: str = "default",
        limit: int = 12,
        allow_private: bool = False,
        permissions: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        """同源相似结果：不依赖 TMDB 的豆瓣/Bangumi 详情也能展示卡片."""
        query = str(title or "").strip()
        if not query:
            record = self.lookup(
                provider,
                external_id,
                media_type=media_type,
                allow_private=allow_private,
                permissions=permissions,
            )
            query = str((record or {}).get("title") or "").strip()
        if not query:
            return []
        hits = self.search(
            query=query,
            provider=provider,
            media_type=media_type,
            content_profile=content_profile,
            limit=max(limit + 2, 14),
            allow_private=allow_private,
            permissions=permissions,
        )
        result = []
        for hit in hits:
            hit_external = str(hit.get("external_id") or hit.get("id") or "")
            if not hit_external or hit_external == str(external_id):
                continue
            item_type = hit.get("media_type") or media_type.value
            result.append(
                {
                    "id": hit_external,
                    "mediaid": (
                        f"DB:{hit_external}"
                        if provider == "douban"
                        else f"BG:{hit_external}"
                        if provider == "bangumi"
                        else hit_external
                    ),
                    "tmdbid": "",
                    "provider": provider,
                    "anchor_provider": provider,
                    "anchor_external_id": hit_external,
                    "title": hit.get("title") or "",
                    "year": hit.get("year") or "",
                    "type": item_type,
                    "image": hit.get("poster") or "",
                    "poster": hit.get("poster") or "",
                    "link": self._registry.provider_detail_url(provider, hit_external, media_type),
                    "fav": "0",
                }
            )
            if len(result) >= limit:
                break
        return result

    def episodes(
        self,
        provider: str,
        external_id: str,
        season: int = 1,
        *,
        allow_private: bool = False,
        permissions: set[str] | None = None,
    ) -> list[dict]:
        """获取非 TMDB 来源的分集（含播出日期），供订阅日历使用."""
        self._ensure_builtin()
        target = self._registry.get_provider(provider)
        if target is None:
            return []
        ref = ProviderRef(
            provider=provider,
            external_id=str(external_id),
            media_type=target.descriptor.default_media_type or MediaType.TV,
            scope="default",
        )
        self._check_visibility([ref], allow_private=allow_private, permissions=permissions)
        runtime = self._orchestrator.runtime_for(target.descriptor)
        try:
            runtime.acquire()
            records = target.episodes(ref, int(season or 1), None)
        except Exception as exc:  # noqa: BLE001 - 单个来源分集失败不阻断日历
            try:
                runtime.record_failure()
            except Exception:  # noqa: BLE001, S110 - 运行时状态失败忽略
                pass
            log.warn(f"[Metadata]分集获取失败 {provider}:{external_id}: {exc}")
            return []
        runtime.record_success()
        return [record.model_dump(mode="json") for record in records]

    def lookup(
        self,
        provider: str,
        external_id: str,
        *,
        media_type: MediaType | None = None,
        scope: str = "default",
        allow_private: bool = False,
        content_profile: str | None = None,
        permissions: set[str] | None = None,
    ) -> dict[str, Any] | None:
        self._ensure_builtin()
        ref = ProviderRef(provider=provider, external_id=str(external_id), media_type=media_type, scope=scope)
        self._check_visibility([ref], allow_private=allow_private, permissions=permissions)
        target = self._registry.get_provider(provider)
        if target is None:
            return None
        version = self._detail_cache_version()
        cache_key = f"v{version}:{provider}:{external_id}:{scope}"
        cached = self._detail_cache.get(cache_key)
        if isinstance(cached, dict):
            return cached
        key = f"{provider}:{external_id}:{scope}"
        with self._inflight_lock:
            future = self._inflight.get(key)
            owner = future is None
            if owner:
                future = Future()
                self._inflight[key] = future
        if not owner:
            # 后续请求等待同一次抓取，不再各自开浏览器。
            try:
                return future.result(timeout=25)
            except Exception:  # noqa: BLE001 - 原请求失败时返回缺失
                return None
        runtime = self._orchestrator.runtime_for(target.descriptor)
        try:
            runtime.acquire()
            record = target.detail(ref, None)
            runtime.record_success()
            data = record.model_dump(mode="json") if record is not None else None
            if isinstance(data, dict) and self._has_detail_payload(data):
                self._detail_cache.set(cache_key, data, ttl=600)
            else:
                self._detail_cache.delete(cache_key)
            future.set_result(data)
            return data
        except ProviderError:
            runtime.record_failure()
            future.set_exception(ProviderError(provider, "详情获取失败"))
            raise
        except Exception as exc:
            runtime.record_failure()
            # 插件可能抛自己的 FetchError；统一包装为 ProviderError，避免冒成 500。
            error = ProviderError(provider, str(exc))
            future.set_exception(error)
            raise error from exc
        finally:
            with self._inflight_lock:
                if self._inflight.get(key) is future:
                    self._inflight.pop(key, None)

    def _detail_cache_version(self) -> int:
        with self._detail_version_lock:
            raw = self._detail_cache.get("__version__")
            try:
                version = int(str(raw)) if raw is not None else 2
            except (TypeError, ValueError):
                version = 2
                self._detail_cache.set("__version__", version)
            return version

    def bump_detail_cache_version(self) -> int:
        """插件配置/优先级/版本变更时递增，旧详情缓存立即失效."""
        with self._detail_version_lock:
            raw = self._detail_cache.get("__version__")
            try:
                current = int(str(raw)) if raw is not None else 2
            except (TypeError, ValueError):
                current = 2
            version = current + 1
            self._detail_cache.set("__version__", version)
            return version

    @staticmethod
    def _has_detail_payload(data: dict[str, Any]) -> bool:
        """只有包含实际元数据的结果才进入缓存，避免缓存空详情."""
        return bool(
            data.get("overview")
            or data.get("genres")
            or data.get("credits")
            or (data.get("images") or {}).get("poster")
        )

    def list_providers(
        self,
        *,
        allow_private: bool = False,
        permissions: set[str] | None = None,
        probe_health: bool = True,
        provider_key: str | None = None,
    ) -> list[dict[str, Any]]:
        self._ensure_builtin()
        runtime = {item["provider"]: item for item in self._orchestrator.runtime_snapshot()}
        visible = []
        for provider in self._registry.list_providers():
            descriptor = provider.descriptor
            if provider_key and descriptor.provider_key != provider_key:
                continue
            if descriptor.visibility == "private":
                required = descriptor.required_permission or "metadata:private:view"
                if not allow_private or (
                    permissions is not None and "*" not in permissions and required not in permissions
                ):
                    continue
            visible.append(provider)

        def probe(provider):
            try:
                return provider.health(None).model_dump(mode="json")
            except Exception as exc:  # noqa: BLE001 - 健康检查失败不阻断列表
                return {
                    "provider": provider.descriptor.provider_key,
                    "ok": False,
                    "message": str(exc),
                }

        if probe_health:
            with ThreadPoolExecutor(max_workers=min(8, len(visible) or 1)) as pool:
                healths = list(pool.map(probe, visible))
        else:
            healths = [{} for _ in visible]

        result = []
        for provider, health in zip(visible, healths):
            descriptor = provider.descriptor
            result.append(
                {
                    "provider": descriptor.provider_key,
                    "name": descriptor.display_name,
                    "capabilities": sorted(str(item) for item in descriptor.capabilities),
                    "media_types": sorted(str(item) for item in descriptor.media_types),
                    "content_profiles": sorted(descriptor.content_profiles),
                    "visibility": descriptor.visibility,
                    "required_permission": descriptor.required_permission,
                    "source_tiers": sorted(str(item) for item in descriptor.source_tiers),
                    "health": health,
                    "runtime": runtime.get(descriptor.provider_key),
                }
            )
        return result

    def metrics(self) -> dict[str, Any]:
        return metrics_snapshot()

    def clear_cache(self) -> None:
        self._orchestrator.clear_cache()

    def save_snapshot(self, identity_id: str, metadata: MediaMetadata, policy_key: str) -> None:
        """保存合成快照（调用方负责 identity 已存在）."""
        providers = sorted({ref.provider for ref in metadata.refs})
        self._identity_repo.save_snapshot(
            identity_id,
            policy_key=policy_key,
            content_profile=metadata.content_profile,
            scope=metadata.scope,
            snapshot_hash=metadata.snapshot_hash,
            payload=metadata.model_dump(mode="json"),
            providers=providers,
        )

    def get_policy(
        self,
        policy: str | None,
        *,
        anchor_provider: str | None = None,
    ) -> MetadataPolicy:
        return resolve_policy(
            policy,
            anchor_provider=anchor_provider,
            system_default=self.system_default_policy,
        )

    def resolve_subscription_policy(self, subscription: Any) -> MetadataPolicy:
        """订阅读路径策略解析：显式设置 > 锚点来源默认 > 系统默认."""
        policy = getattr(subscription, "metadata_policy", None) or getattr(subscription, "METADATA_POLICY", None)
        anchor = getattr(subscription, "anchor_provider", None) or getattr(subscription, "ANCHOR_PROVIDER", None)
        return self.get_policy(policy, anchor_provider=anchor)

    def _ensure_builtin(self) -> None:
        if self._builtin_ready:
            return
        with self._builtin_lock:
            if self._builtin_ready:
                return
            register_builtin_providers(self._registry)
            self._builtin_ready = True

    def _check_visibility(
        self,
        refs: list[ProviderRef],
        *,
        allow_private: bool,
        permissions: set[str] | None = None,
    ) -> None:
        for ref in refs:
            provider = self._registry.get_provider(ref.provider)
            if provider is None or provider.descriptor.visibility != "private":
                continue
            if not allow_private:
                raise ValidationError(f"无权访问私有来源: {ref.provider}")
            required = getattr(provider.descriptor, "required_permission", "") or "metadata:private:view"
            if permissions is not None and "*" not in permissions and required not in permissions:
                raise ValidationError(f"缺少权限 {required}")

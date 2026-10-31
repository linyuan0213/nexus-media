"""探索页发现服务：来源列表 + feed 聚合."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from typing import Any

from loguru import logger

from app.core.exceptions import ValidationError
from app.media.display_image_policy import transform_display_image
from app.media.metadata.models import DiscoveryPage
from app.media.metadata.providers.discovery import BangumiDiscovery, DoubanDiscovery, TmdbDiscovery
from app.media.metadata.registry import MetadataRegistry
from app.media.metadata.registry import registry as global_registry
from app.services.library_presence_service import LibraryPresenceService


class DiscoveryService:
    """API → DiscoveryService → DiscoveryProvider."""

    def __init__(
        self,
        *,
        registry: MetadataRegistry | None = None,
        media_service: Any = None,
        media_server: Any = None,
        library_presence_service: LibraryPresenceService | None = None,
        register_builtins: bool = True,
        cache_ttl_seconds: int = 300,
    ) -> None:
        self._registry = registry or global_registry
        self._media_service = media_service
        self._media_server = media_server
        self._library_presence = library_presence_service or LibraryPresenceService(media_server=media_server)
        self._builtin_lock = threading.Lock()
        self._builtin_ready = not register_builtins
        self._cache_ttl = max(0, cache_ttl_seconds)
        self._cache: dict[str, tuple[datetime, DiscoveryPage]] = {}
        self._cache_lock = threading.Lock()

    def list_sources(
        self,
        *,
        allow_private: bool = False,
        permissions: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        self._ensure_builtin()
        sources = []
        for provider in self._registry.list_discovery_providers():
            descriptor = provider.descriptor
            if descriptor.visibility == "private":
                required = getattr(descriptor, "required_permission", "") or "metadata:private:view"
                if not allow_private or (permissions is not None and required not in permissions):
                    continue
            sources.append(
                {
                    "provider": descriptor.provider_key,
                    "name": descriptor.display_name,
                    "visibility": descriptor.visibility,
                    "feeds": [feed.model_dump(mode="json") for feed in provider.feeds(None)],
                }
            )
        return sources

    def items(
        self,
        provider: str,
        feed: str,
        *,
        page: int = 1,
        filters: dict | None = None,
        allow_private: bool = False,
        permissions: set[str] | None = None,
    ) -> DiscoveryPage:
        self._ensure_builtin()
        target = self._registry.get_discovery_provider(provider)
        if target is None:
            raise ValidationError(f"未知发现来源: {provider}")
        if target.descriptor.visibility == "private":
            required = getattr(target.descriptor, "required_permission", "") or "metadata:private:view"
            if not allow_private:
                raise ValidationError(f"无权访问私有来源: {provider}")
            if permissions is not None and required not in permissions:
                raise ValidationError(f"缺少权限 {required}")
        feeds = {item.key for item in target.feeds(None)}
        if feed not in feeds:
            raise ValidationError(f"未知 feed: {provider}/{feed}")
        cache_key = json.dumps(
            {"provider": provider, "feed": feed, "page": max(1, page), "filters": filters or {}},
            sort_keys=True,
            ensure_ascii=False,
        )
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        try:
            result = target.items(feed, max(1, page), filters or {}, None)
        except Exception as exc:  # noqa: BLE001 - 插件抓取失败返回可重试错误页
            logger.warning(f"[Discovery] {provider}/{feed} 抓取失败: {exc}")
            return DiscoveryPage(
                items=[],
                page=max(1, page),
                error=str(exc)[:300] or "内容抓取失败",
                retryable=True,
            )
        result = self._dedupe_items(result)
        for discovery_item in result.items:
            profile = str(getattr(discovery_item, "content_profile", "") or "")
            if getattr(discovery_item, "poster", None):
                discovery_item.poster = transform_display_image(profile, str(discovery_item.poster))
            if getattr(discovery_item, "backdrop", None):
                discovery_item.backdrop = transform_display_image(profile, str(discovery_item.backdrop))
        self._library_presence.annotate(result.items)
        # 错误页不进入 5 分钟缓存，否则预热完成后用户仍会看到旧错误。
        if not result.error:
            self._cache_put(cache_key, result)
        return result

    @staticmethod
    def _dedupe_items(page: DiscoveryPage) -> DiscoveryPage:
        """按内容锚点去重，合并同番号的不同版本（如 Blu-ray / 通常版）."""
        seen: set[str] = set()
        items = []
        for item in page.items:
            anchor = item.anchor_ref
            if anchor is not None and anchor.external_id:
                key = f"{anchor.provider}:{anchor.external_id}"
            else:
                key = f"{item.provider}:{item.ref.external_id or item.title}"
            if key in seen:
                continue
            seen.add(key)
            items.append(item)
        if len(items) == len(page.items):
            return page
        return page.model_copy(update={"items": items})

    def clear_cache(self) -> None:
        with self._cache_lock:
            self._cache.clear()

    def _cache_get(self, key: str) -> DiscoveryPage | None:
        if not self._cache_ttl:
            return None
        with self._cache_lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            created, page = entry
            if datetime.now() - created > timedelta(seconds=self._cache_ttl):
                self._cache.pop(key, None)
                return None
            return page

    def _cache_put(self, key: str, page: DiscoveryPage) -> None:
        # 空页/错误页通常是站点挑战或瞬时失败，不缓存，避免一直显示无内容。
        if not self._cache_ttl or not page.items or page.error:
            return
        with self._cache_lock:
            self._cache[key] = (datetime.now(), page)

    def _ensure_builtin(self) -> None:
        if self._builtin_ready:
            return
        with self._builtin_lock:
            if self._builtin_ready:
                return
            self._registry.register_discovery_provider(DoubanDiscovery())
            if self._media_service is not None:
                self._registry.register_discovery_provider(TmdbDiscovery(self._media_service))
            self._registry.register_discovery_provider(BangumiDiscovery())
            self._builtin_ready = True

"""媒体库入库状态统一判定.

优先级固定为：转移成功 → 媒体库同步索引 → 多实例实时检查。
探索页、后续媒体卡片等入口只消费本服务，不各自拼查询逻辑。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import monotonic
from typing import Any

from loguru import logger

from app.db.repositories.media_identity_repository import MediaIdentityRepository
from app.db.repositories.media_sync_repo_adapter import MediaSyncRepositoryAdapter
from app.db.repositories.transfer_repository import TransferRepository


class LibraryPresenceService:
    """批量标记媒体是否已入库."""

    def __init__(
        self,
        transfer_repo: Any = None,
        media_sync_repo: Any = None,
        media_server: Any = None,
        identity_repo: Any = None,
        *,
        live_workers: int = 4,
        live_ttl: int = 300,
        warm_in_background: bool = True,
    ) -> None:
        self._transfer_repo = transfer_repo or TransferRepository()
        self._media_sync_repo = media_sync_repo or MediaSyncRepositoryAdapter()
        self._identity_repo = identity_repo or MediaIdentityRepository()
        self._media_server = media_server
        self._live_workers = max(1, live_workers)
        self._live_ttl = max(1, live_ttl)
        self._warm_in_background = warm_in_background
        self._live_cache: dict[tuple[str, str], tuple[float, bool]] = {}
        self._live_pending: set[tuple[str, str]] = set()
        self._live_lock = Lock()
        self._warm_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="library-presence-warm")

    @staticmethod
    def _pair(item: Any) -> tuple[str, str]:
        for ref in (getattr(item, "anchor_ref", None), getattr(item, "ref", None)):
            provider = str(getattr(ref, "provider", "") or "").strip()
            external = str(getattr(ref, "external_id", "") or "").strip()
            if provider and external:
                return provider, external
        return "", ""

    def annotate(self, items: list[Any]) -> None:
        """原地写入 item.extra['in_library']."""
        unresolved: list[tuple[Any, tuple[str, str]]] = []
        for item in items:
            pair = self._pair(item)
            if pair[0]:
                unresolved.append((item, pair))
        if not unresolved:
            return

        # 1) 直接锚点：转移历史
        present = self._batch_query(self._transfer_repo, [pair for _, pair in unresolved], "转移历史")
        remaining = []
        for item, pair in unresolved:
            if pair in present:
                self._set(item)
            else:
                remaining.append((item, pair))
        if not remaining:
            return

        # 2) content_id 虚拟锚点：通过身份图解析到具体 provider
        identity_map = self._resolve_identity_ids(remaining)
        transfer_identity_ids = self._batch_identity_query(self._transfer_repo, set(identity_map.values()), "转移历史")
        remaining = self._mark_by_identity(remaining, identity_map, transfer_identity_ids)
        if not remaining:
            return

        # 3) 直接锚点：媒体库同步索引
        sync_present = self._batch_query(self._media_sync_repo, [pair for _, pair in remaining], "媒体库同步索引")
        still: list[tuple[Any, tuple[str, str]]] = []
        for item, pair in remaining:
            if pair in sync_present:
                self._set(item)
            else:
                still.append((item, pair))
        remaining = still
        if not remaining:
            return

        # 4) 身份 ID：媒体库同步索引
        sync_identity_ids = self._batch_identity_query(
            self._media_sync_repo, set(identity_map.values()), "媒体库同步索引"
        )
        remaining = self._mark_by_identity(remaining, identity_map, sync_identity_ids)
        if not remaining:
            return

        # 5) 实时媒体服务器兜底
        if self._media_server is None:
            return
        immediate = []
        for item, _pair in remaining:
            cached = self._cached_live(item)
            if cached is True:
                self._set(item)
            elif cached is None:
                immediate.append(item)
        if not immediate:
            return
        if self._warm_in_background:
            for item in immediate:
                self._schedule_warm(item)
            return
        with ThreadPoolExecutor(max_workers=min(self._live_workers, len(immediate))) as executor:
            results = list(executor.map(self._check_live, immediate))
        for item, found in zip(immediate, results, strict=False):
            if found:
                self._set(item)

    def _resolve_identity_ids(self, items: list[tuple[Any, tuple[str, str]]]) -> dict[tuple[str, str], str]:
        """把 content_id 虚拟锚点解析为身份 ID；插件通常把身份挂到 content_profile 下."""
        result: dict[tuple[str, str], str] = {}
        for item, pair in items:
            anchor = getattr(item, "anchor_ref", None)
            if anchor is None or str(getattr(anchor, "provider", "") or "") != "content_id":
                continue
            external = str(getattr(anchor, "external_id", "") or "").strip()
            if not external:
                continue
            profile = str(getattr(item, "content_profile", "") or "default").strip() or "default"
            scope = str(getattr(anchor, "scope", "") or "default").strip() or "default"
            providers = [profile] if profile == "content_id" else [profile, "content_id"]
            for provider in dict.fromkeys(providers):
                for current_scope in dict.fromkeys([scope, "default"]):
                    try:
                        identity = self._identity_repo.find_by_ref(
                            provider,
                            external,
                            scope=current_scope,
                            media_type=str(getattr(anchor, "media_type", "") or "") or None,
                        )
                    except Exception:  # noqa: BLE001 - 身份查询失败继续兜底
                        identity = None
                    if identity is not None:
                        result[pair] = str(getattr(identity, "IDENTITY_ID", "") or "")
                        break
                if pair in result:
                    break
        return {pair: identity_id for pair, identity_id in result.items() if identity_id}

    def _batch_identity_query(self, repo: Any, identity_ids: set[str], label: str) -> set[str]:
        if not identity_ids:
            return set()
        method = getattr(repo, "get_existing_identity_ids", None)
        if method is None:
            return set()
        try:
            return {str(item) for item in method(sorted(identity_ids)) if item}
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[LibraryPresence]{label}身份查询失败: {exc}")
            return set()

    def _mark_by_identity(
        self,
        items: list[tuple[Any, tuple[str, str]]],
        identity_map: dict[tuple[str, str], str],
        present_identity_ids: set[str],
    ) -> list[tuple[Any, tuple[str, str]]]:
        remaining = []
        for item, pair in items:
            identity_id = identity_map.get(pair)
            if identity_id and identity_id in present_identity_ids:
                self._set(item)
            else:
                remaining.append((item, pair))
        return remaining

    def warm(self, items: list[Any]) -> None:
        """后台预热入口：提前把媒体库存在性写入短 TTL 缓存."""
        if self._media_server is None:
            return
        with ThreadPoolExecutor(max_workers=min(self._live_workers, max(1, len(items)))) as executor:
            list(executor.map(self._check_live, items))

    @staticmethod
    def _set(item: Any) -> None:
        item.extra = {**(getattr(item, "extra", None) or {}), "in_library": True}

    def _batch_query(self, repo: Any, pairs: list[tuple[str, str]], label: str) -> set[tuple[str, str]]:
        try:
            return repo.get_existing_anchors(list(dict.fromkeys(pairs)))
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[LibraryPresence]{label}查询失败: {exc}")
            return set()

    def _cache_key(self, item: Any) -> tuple[str, str]:
        return self._pair(item)

    def _cached_live(self, item: Any) -> bool | None:
        key = self._cache_key(item)
        with self._live_lock:
            entry = self._live_cache.get(key)
        if entry is None or entry[0] <= monotonic():
            return None
        return entry[1]

    def _schedule_warm(self, item: Any) -> None:
        key = self._cache_key(item)
        if not key[0]:
            return
        with self._live_lock:
            if key in self._live_pending or key in self._live_cache:
                return
            self._live_pending.add(key)
        self._warm_executor.submit(self._warm_one, item, key)

    def _warm_one(self, item: Any, key: tuple[str, str]) -> None:
        try:
            self._check_live(item)
        finally:
            with self._live_lock:
                self._live_pending.discard(key)

    def _check_live(self, item: Any) -> bool:
        if self._media_server is None:
            return False
        anchor = getattr(item, "anchor_ref", None) or getattr(item, "ref", None)
        external = str(getattr(anchor, "external_id", "") or "")
        try:
            media_type = str(getattr(getattr(anchor, "media_type", None), "value", None) or "movie")
            found = bool(
                self._media_server.check_library_present_any(
                    media_type,
                    title=getattr(item, "title", None),
                    year=getattr(item, "year", None),
                    content_profile=getattr(item, "content_profile", None),
                    alternate_titles=[external] if external else [],
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[LibraryPresence]实时媒体库检查失败: {exc}")
            found = False
        key = self._cache_key(item)
        with self._live_lock:
            self._live_cache[key] = (monotonic() + self._live_ttl, found)
        return found

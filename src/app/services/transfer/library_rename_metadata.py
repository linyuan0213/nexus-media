"""批量重命名元数据解析编排."""

from __future__ import annotations

import os
import posixpath
from typing import Any

import log
from app.domain.media_types import ProviderMediaType
from app.media.parser import meta_info
from app.services.transfer.library_rename_models import RenameScope, ResolvedMetadata
from app.services.transfer.library_rename_nfo import collect_nfo
from app.services.transfer.library_rename_sources import (
    apply_online,
    apply_source,
    finalize_media,
    from_cache,
    from_download_history,
    from_filename,
    from_history,
    from_media_server,
    from_nfo,
    from_online,
    merge_missing,
    parse_season_episode,
)
from app.storage.backends.base import StorageBackend
from app.utils import PathUtils

_PRIORITY = {
    "history": 100,
    "cache_manual": 98,
    "cache": 90,
    "nfo": 80,
    "download_history": 70,
    "mediaserver": 60,
    "online": 55,
    "filename": 50,
}


class LibraryMetadataResolver:
    """按 ADR-024 的优先级解析库内文件元数据."""

    def __init__(self, media_server, rename_repo, download_repo, metadata_gateway=None):
        self._media_server = media_server
        self._repo = rename_repo
        self._download_repo = download_repo
        self._metadata_gateway = metadata_gateway
        self._ms_exact: dict[str, dict[str, Any]] = {}
        self._ms_series: list[tuple[str, dict[str, Any]]] = []
        self._ms_loaded = False

    def prepare(self, use_media_server: bool, server_id: int | None = None) -> None:
        if not use_media_server or self._ms_loaded:
            return
        self._ms_loaded = True
        try:
            libraries = self._media_server.get_libraries(server_id) or []
        except Exception as e:  # noqa: BLE001
            log.warn(f"[LibraryRename]读取媒体服务器媒体库失败: {e}")
            return
        for library in libraries:
            library_id = library.get("id") if isinstance(library, dict) else None
            if not library_id:
                continue
            try:
                items = self._media_server.get_items(library_id, server_id) or []
                for item in items:
                    self._index_item(item)
            except Exception as e:  # noqa: BLE001
                log.warn(f"[LibraryRename]读取媒体服务器条目失败 {library_id}: {e}")

    def resolve(
        self,
        backend: StorageBackend,
        path: str,
        hint: ProviderMediaType,
        scope: RenameScope,
    ) -> ResolvedMetadata | None:
        directory = posixpath.dirname(path)
        base_name = posixpath.basename(path)
        candidates: list[ResolvedMetadata] = []

        rows = self._repo.get_history_by_dest(directory, base_name)
        if rows:
            history = from_history(rows[0], hint)
            if history:
                history.history_ids = [int(row["ID"]) for row in rows if row.get("ID")]
                candidates.append(history)

        cache_row = self._repo.get_metadata(backend.id, path)
        if cache_row:
            cached = from_cache(cache_row, backend, path)
            if cached and (cached.is_manual or cached.confidence == "high"):
                cached.origin = "cache"
                candidates.append(cached)

        download = self._from_download_history(path, hint)
        if download:
            candidates.append(download)

        nfo = collect_nfo(backend, directory, os.path.splitext(base_name)[0], hint)
        nfo_candidate = from_nfo(nfo or {}, hint)
        if nfo_candidate:
            candidates.append(nfo_candidate)

        server_item = self._match_media_server(path)
        server_candidate = from_media_server(server_item or {}, hint)
        if server_candidate:
            candidates.append(server_candidate)

        filename_candidate = from_filename(path, hint)
        if filename_candidate:
            candidates.append(filename_candidate)

        if scope.reidentify_no_metadata:
            online_candidate = from_online(path, backend, hint, self._metadata_gateway)
            if online_candidate:
                candidates.append(online_candidate)

        if not candidates:
            return None

        candidates.sort(key=lambda item: _PRIORITY.get(self._priority_key(item), 0), reverse=True)
        chosen = candidates[0]
        for candidate in candidates[1:]:
            merge_missing(chosen.media, candidate.media)
            if not chosen.episode_title and candidate.episode_title:
                chosen.episode_title = candidate.episode_title
            if not chosen.en_title and candidate.en_title:
                chosen.en_title = candidate.en_title
            if not chosen.source_filename and candidate.source_filename:
                chosen.source_filename = candidate.source_filename

        try:
            apply_source(chosen.media, chosen.source_filename)
        except Exception as e:  # noqa: BLE001
            log.debug(f"[LibraryRename]解析原始下载名失败 {chosen.source_filename}: {e}")
        finalize_media(chosen.media, hint)

        if scope.allow_online_metadata or chosen.source == "online":
            apply_online(chosen, self._metadata_gateway)
            finalize_media(chosen.media, hint)
        return chosen

    def _priority_key(self, item: ResolvedMetadata) -> str:
        if item.is_manual:
            return "cache_manual"
        if item.origin == "cache":
            return "cache"
        return item.source

    def _from_download_history(self, path: str, hint: ProviderMediaType) -> ResolvedMetadata | None:
        base_name = posixpath.basename(path)
        directory = posixpath.dirname(path)
        entity = self._download_repo.get_by_path(path) or self._download_repo.get_by_path(directory)
        if entity:
            candidate = from_download_history(entity, base_name, hint, exact=True)
            if candidate:
                return candidate

        parsed = meta_info(base_name, mtype=hint)
        if not parsed:
            return None
        title = parsed.title or parsed.get_name()
        if not title:
            return None
        rows = self._download_repo.get_by_title(title) or []
        filtered = []
        for row in rows:
            row_type = ProviderMediaType.from_value(str(getattr(row, "media_type", "") or ""))
            if hint != ProviderMediaType.UNKNOWN and row_type != ProviderMediaType.UNKNOWN and row_type != hint:
                continue
            row_year = str(getattr(row, "year", "") or "")
            if parsed.year and row_year and parsed.year != row_year:
                continue
            filtered.append(row)
        if not filtered:
            return None

        if len(filtered) == 1:
            return from_download_history(filtered[0], base_name, hint, exact=False)

        season, _, episode, _ = parse_season_episode(base_name)
        if season is not None and episode is not None:
            by_episode = [
                row
                for row in filtered
                if getattr(row, "parsed_season", None) == season
                and episode in (getattr(row, "parsed_episodes", []) or [])
            ]
            if len(by_episode) == 1:
                return from_download_history(by_episode[0], base_name, hint, exact=False)

        by_name = [
            row
            for row in filtered
            if posixpath.splitext(posixpath.basename(str(getattr(row, "torrent", "") or "")))[0].lower()
            == posixpath.splitext(base_name)[0].lower()
        ]
        if len(by_name) == 1:
            return from_download_history(by_name[0], base_name, hint, exact=False)
        return None

    def _index_item(self, item: Any) -> None:
        if not item or not isinstance(item, dict) or not item.get("path"):
            return
        normalized = _norm(item["path"])
        item_type = str(item.get("type") or "").lower()
        if item_type == "movie":
            self._ms_exact[normalized] = item
        elif item_type in ("series", "show", "tv", "anime"):
            self._ms_series.append((normalized, item))

    def _match_media_server(self, path: str) -> dict[str, Any] | None:
        if not self._ms_loaded:
            return None
        normalized = _norm(path)
        item = self._ms_exact.get(normalized)
        if item:
            return item
        for prefix, series in sorted(self._ms_series, key=lambda pair: len(pair[0]), reverse=True):
            if PathUtils.is_path_in_path(prefix, normalized):
                return series
        return None


def _norm(path: str) -> str:
    return posixpath.normpath(str(path or "").replace("\\", "/"))

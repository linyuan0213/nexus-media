"""批量重命名扫描、路径计算与计划生成."""

from __future__ import annotations

import os
import re
from typing import Any

import log
from app.core.constants import RMT_FAVTYPE, RMT_MEDIAEXT
from app.core.exceptions import ValidationError
from app.db.repositories.library_rename_repository import path_hash
from app.domain.mediatypes import MediaType
from app.media.metadata.naming import naming_field_keys
from app.media.scraper.media_library import MediaLibrary
from app.services.transfer.library_rename_metadata import LibraryMetadataResolver
from app.services.transfer.library_rename_models import LibraryRoot, RenameScope, ResolvedMetadata
from app.services.transfer.name_format import parse_fields, validate
from app.services.transfer.path_resolver import TransferPathResolver
from app.storage import LocalStorageBackend, StorageBackendFactory
from app.storage.backends.base import StorageBackend, StorageType
from app.storage.config_models import LocalStorageConfig
from app.utils import PathUtils
from app.utils.json_utils import JsonUtils

_MEDIA_CFG_KEYS = {
    MediaType.MOVIE: ("movie_path", "movie_backend"),
    MediaType.TV: ("tv_path", "tv_backend"),
    MediaType.ANIME: ("anime_path", "anime_backend"),
}
_EXCLUDED_SEGMENTS = {"#recycle", ".trash", "@eadir", "recycle"}


class _FormatMetaService:
    """只读适配器：把计划快照中的联网字段提供给 get_format_dict."""

    def __init__(self, episode_title: str | None, en_title: str | None):
        self._episode_title = episode_title or ""
        self._en_title = en_title or ""

    def get_episode_title(self, media) -> str:
        return self._episode_title

    def en_title(self, media) -> str:
        return self._en_title


class LibraryRenamePlanner:
    """负责扫描媒体库、解析元数据并生成可执行计划."""

    def __init__(
        self,
        media_config_service,
        storage_repo,
        metadata_resolver: LibraryMetadataResolver,
        media_service,
        category_repo,
        metadata_gateway=None,
    ):
        self._metadata_gateway = metadata_gateway
        self._media_config_service = media_config_service
        self._storage_repo = storage_repo
        self._metadata = metadata_resolver
        self._media_service = media_service
        self._category_repo = category_repo
        self._category_names: dict[str, set[str]] = {}
        self._resolver: TransferPathResolver | None = None
        self._movie_fields: set[str] = set()
        self._tv_fields: set[str] = set()

    def prepare(self, scope: RenameScope) -> dict[str, Any]:
        self._resolver = TransferPathResolver.from_settings(self._media_config_service)
        resolver = self._resolver
        cfg = self._media_config_service.get_config()
        movie_fmt = _join_format(resolver._movie_dir_rmt_format, resolver._movie_file_rmt_format)
        tv_fmt = _join_format(
            resolver._tv_dir_rmt_format,
            resolver._tv_season_rmt_format,
            resolver._tv_file_rmt_format,
        )
        for name, fmt in (("movie_name_format", movie_fmt), ("tv_name_format", tv_fmt)):
            result = validate(fmt, naming_field_keys())
            if not result["ok"]:
                raise ValidationError(f"{name} 格式非法: {'; '.join(result['problems'])}")
        self._movie_fields = set(parse_fields(movie_fmt))
        self._tv_fields = set(parse_fields(tv_fmt))
        self._category_names = self._load_categories()
        self._metadata.prepare(scope.use_mediaserver_metadata, server_id=scope.server_id)
        return {
            "movie_name_format": movie_fmt,
            "tv_name_format": tv_fmt,
            "movie_category_flag": bool(getattr(resolver, "_movie_category_flag", False)),
            "tv_category_flag": bool(getattr(resolver, "_tv_category_flag", False)),
            "anime_category_flag": bool(getattr(resolver, "_anime_category_flag", False)),
            "movie_path": cfg.get("movie_path") or [],
            "tv_path": cfg.get("tv_path") or [],
            "anime_path": cfg.get("anime_path") or [],
            "movie_backend": cfg.get("movie_backend") or [],
            "tv_backend": cfg.get("tv_backend") or [],
            "anime_backend": cfg.get("anime_backend") or [],
        }

    def build_items(self, scope: RenameScope) -> list[dict[str, Any]]:
        roots = self._build_roots(scope)
        if not roots:
            return []
        files: list[tuple[LibraryRoot, str]] = []
        seen: set[tuple[str, str]] = set()
        for root in roots:
            count = 0
            scan_backend = None if normalize_backend(root.backend_id) == "local" else root.backend
            paths = (
                MediaLibrary.get_library_files(root.root)
                if scan_backend is None
                else self._iter_remote_files(root.root, scan_backend)
            )
            for path in paths:
                if self._excluded(os.path.relpath(path, root.root)):
                    continue
                if scope.roots and not any(PathUtils.is_path_in_path(prefix, path) for prefix in scope.roots):
                    continue
                key = (str(root.backend_id), _norm(path))
                if key in seen:
                    continue
                seen.add(key)
                files.append((root, _norm(path)))
                count += 1
                if len(files) >= max(1, int(scope.limit)):
                    break
            if len(files) >= max(1, int(scope.limit)):
                break
            log.debug(f"[LibraryRename]扫描 {root.root}: {count} 个媒体文件")
        files.sort(key=lambda pair: pair[1])
        items = [self._plan_one(root, path, scope) for root, path in files]
        self._mark_conflicts(items)
        return items

    def _iter_remote_files(self, root: str, backend: StorageBackend):
        """远程后端递归遍历；避免复用会直接返回目录的 MediaLibrary 远程实现."""
        visited: set[str] = set()

        def walk(directory: str):
            normalized = _norm(directory)
            if normalized in visited:
                return
            visited.add(normalized)
            try:
                entries = list(backend.list_dir(directory))
            except Exception as e:  # noqa: BLE001
                log.warn(f"[LibraryRename]遍历远程目录失败 {directory}: {e}")
                return
            for entry in entries:
                if entry.is_dir:
                    yield from walk(entry.path)
                elif os.path.splitext(entry.path)[1].lower() in RMT_MEDIAEXT:
                    yield _norm(entry.path)

        yield from walk(root)

    # ---------- roots ----------

    def _build_roots(self, scope: RenameScope) -> list[LibraryRoot]:
        cfg = self._media_config_service.get_config()
        roots: list[LibraryRoot] = []
        seen: set[tuple[str, str]] = set()
        for media_type in (MediaType.MOVIE, MediaType.TV, MediaType.ANIME):
            if media_type not in scope.media_types:
                continue
            paths_key, backend_key = _MEDIA_CFG_KEYS[media_type]
            paths = cfg.get(paths_key) or []
            backend_ids = cfg.get(backend_key) or []
            for index, root in enumerate(paths):
                if not root:
                    continue
                if scope.roots and not any(
                    PathUtils.is_path_in_path(root, prefix) or PathUtils.is_path_in_path(prefix, root)
                    for prefix in scope.roots
                ):
                    continue
                backend_id = str(backend_ids[index]) if index < len(backend_ids) and backend_ids[index] else "local"
                key = (normalize_backend(backend_id), _norm(root))
                if key in seen:
                    continue
                seen.add(key)
                backend = self._resolve_backend(backend_id)
                if backend is None:
                    log.warn(f"[LibraryRename]跳过不可用媒体库根 {root} (backend={backend_id})")
                    continue
                try:
                    info = backend.stat(root)
                except Exception as e:  # noqa: BLE001
                    log.warn(f"[LibraryRename]读取媒体库根信息失败 {root}: {e}")
                    continue
                local = normalize_backend(backend_id) == "local"
                if local:
                    if info is None or not info.is_dir:
                        log.warn(f"[LibraryRename]媒体库根不存在或不是目录: {root}")
                        continue
                elif info is not None and not info.is_dir:
                    log.warn(f"[LibraryRename]媒体库根不是目录: {root}")
                    continue
                elif info is None:
                    try:
                        next(iter(backend.list_dir(root)))
                    except StopIteration:
                        pass
                    except Exception as e:  # noqa: BLE001
                        log.warn(f"[LibraryRename]媒体库根不可访问 {root}: {e}")
                        continue
                roots.append(
                    LibraryRoot(
                        media_type=media_type,
                        root=_norm(root),
                        backend_id=backend_id,
                        backend=backend,
                    )
                )
        return roots

    def _resolve_backend(self, backend_id: str) -> StorageBackend | None:
        normalized = normalize_backend(backend_id)
        if normalized == "local":
            return LocalStorageBackend(LocalStorageConfig(id="local", name="本地", type=StorageType.LOCAL))
        try:
            entity = self._storage_repo.get_by_id(int(normalized))
        except (TypeError, ValueError):
            return None
        if not entity or not entity.enabled:
            return None
        info = StorageBackendFactory.get_config_info(entity.type)
        stype, cls = info if info else (StorageType.LOCAL, LocalStorageConfig)
        config = cls(id=str(entity.id), name=entity.name, type=stype, enabled=entity.enabled)
        for key, value in (entity.config or {}).items():
            if hasattr(config, key):
                setattr(config, key, value)
        try:
            return StorageBackendFactory.create(config)
        except Exception as e:  # noqa: BLE001
            log.warn(f"[LibraryRename]创建存储后端失败 {backend_id}: {e}")
            return None

    # ---------- one file ----------

    def _plan_one(self, root: LibraryRoot, path: str, scope: RenameScope) -> dict[str, Any]:
        base_name = os.path.basename(path)
        base_item = {
            "BACKEND_ID": normalize_backend(root.backend_id),
            "ROOT": root.root,
            "OLD_PATH": path,
            "NEW_PATH": None,
            "OLD_PATH_HASH": self._hash(path),
            "OLD_SIZE": None,
            "OLD_MTIME": None,
            "METADATA_SOURCE": "",
            "METADATA_SNAPSHOT": "{}",
            "ACTION": "skip",
            "STATUS": "planned",
            "DIRECTORY_MOVE_ID": None,
            "AUX_MOVES": None,
            "REASON": None,
            "ERROR": None,
            "ROLLBACK_STATUS": None,
        }
        try:
            stat = root.backend.stat(path)
        except Exception as e:  # noqa: BLE001
            log.debug(f"[LibraryRename]读取文件信息失败 {path}: {e}")
            stat = None
        base_item["OLD_SIZE"] = stat.size if stat else None
        base_item["OLD_MTIME"] = stat.mtime if stat else None
        if stat is None:
            base_item["REASON"] = "file_missing"
            return base_item
        try:
            resolved = self._metadata.resolve(root.backend, path, root.media_type, scope)
        except Exception as e:  # noqa: BLE001
            log.warn(f"[LibraryRename]解析元数据失败 {path}: {e}")
            base_item["ACTION"] = "needs_metadata"
            base_item["REASON"] = "metadata_error"
            return base_item
        if not resolved:
            base_item["ACTION"] = "needs_metadata"
            base_item["REASON"] = "no_metadata"
            return base_item

        media_type = resolved.media.type or root.media_type
        resolved.media.type = media_type
        base_item["METADATA_SOURCE"] = resolved.source
        snapshot = resolved.snapshot()
        base_item["METADATA_SNAPSHOT"] = JsonUtils.dumps(snapshot, ensure_ascii=False)

        reason = self._required_field_reason(resolved, media_type, base_name)
        if reason:
            base_item["REASON"] = reason
            if reason == "missing_season_episode":
                base_item["ACTION"] = "needs_metadata"
            return base_item

        try:
            new_path, reason = self._compute_path(root, path, resolved, scope)
        except Exception as e:  # noqa: BLE001
            log.warn(f"[LibraryRename]计算目标路径失败 {path}: {e}")
            new_path, reason = None, "path_error"
        if reason or not new_path:
            base_item["REASON"] = reason or "empty_path"
            return base_item
        snapshot["target_category"] = resolved.media.category or ""
        snapshot["update_category"] = bool(scope.reorganize_category)
        base_item["METADATA_SNAPSHOT"] = JsonUtils.dumps(snapshot, ensure_ascii=False)
        base_item["NEW_PATH"] = new_path
        if _norm(new_path) == _norm(path):
            base_item["ACTION"] = "unchanged"
            return base_item
        if root.backend.exists(new_path):
            base_item["ACTION"] = "conflict"
            base_item["REASON"] = "target_exists"
            return base_item
        base_item["ACTION"] = "rename"
        return base_item

    def _required_field_reason(self, resolved: ResolvedMetadata, media_type: MediaType, base_name: str) -> str | None:
        meta = resolved.media
        fields = self._movie_fields if media_type == MediaType.MOVIE else self._tv_fields
        if not meta.title:
            return "missing_title"
        if "year" in fields and not meta.year:
            return "missing_year"
        if "tmdbid" in fields and not meta.tmdb_id and meta.get_media_ref() is None:
            return "missing_tmdbid"
        if "original_name" in fields and not meta.org_string:
            return "missing_original_name"
        if "rev_name" in fields and not meta.rev_string:
            return "missing_rev_name"
        if "en_title" in fields and not resolved.en_title:
            return "missing_en_title"
        if "episode_title" in fields and not resolved.episode_title:
            return "missing_episode_title"
        if "original_title" in fields and not meta.original_title:
            return "missing_original_title"
        if "imdbid" in fields and not meta.imdb_id:
            return "missing_imdbid"
        if (
            "part" in fields
            and not meta.part
            and (detect_part_hint(meta.org_string or "") or detect_part_hint(base_name))
        ):
            return "missing_part"
        if media_type != MediaType.MOVIE:
            if meta.begin_season is None or meta.begin_episode is None:
                return "missing_season_episode"
            if any(field in fields for field in ("season", "episode", "season_episode")):
                return None
        return None

    def _compute_path(
        self,
        root: LibraryRoot,
        old_path: str,
        resolved: ResolvedMetadata,
        scope: RenameScope,
    ) -> tuple[str | None, str | None]:
        resolver = self._resolver
        if resolver is None:
            return None, "planner_not_ready"
        meta = resolved.media
        adapter = _FormatMetaService(resolved.episode_title, resolved.en_title)
        snapshot = (
            self._metadata_gateway.latest_snapshot_for_media(meta, context=None)
            if self._metadata_gateway is not None
            else None
        )
        ext = os.path.splitext(old_path)[1]
        if scope.layout_mode == "filename_only":
            if meta.type == MediaType.MOVIE:
                _, file_name = resolver.get_movie_dest_path(meta, adapter, snapshot)
            else:
                _, _, file_name = resolver.get_tv_dest_path(meta, adapter, snapshot)
            file_name = self._fallback_filename(file_name, old_path)
            if not file_name:
                return None, "empty_filename"
            new_path = os.path.join(os.path.dirname(old_path), file_name + ext)
        elif scope.reorganize_category:
            if meta.type == MediaType.MOVIE:
                _, file_name = resolver.get_movie_dest_path(meta, adapter, snapshot)
            else:
                _, _, file_name = resolver.get_tv_dest_path(meta, adapter, snapshot)
            new_dir = resolver.get_dest_path_by_info(root.root, meta, adapter, snapshot)
            file_name = self._fallback_filename(file_name, old_path)
            if not new_dir or not file_name:
                return None, "empty_filename"
            new_path = os.path.join(new_dir, file_name + ext)
        else:
            prefix = self._current_category(root, old_path, meta.type)
            fields = self._movie_fields if meta.type == MediaType.MOVIE else self._tv_fields
            category_in_format = "category" in fields
            meta.category = prefix or ""
            if meta.type == MediaType.MOVIE:
                sub_dir, file_name = resolver.get_movie_dest_path(meta, adapter, snapshot)
                new_dir = (
                    os.path.join(root.root, sub_dir)
                    if category_in_format
                    else (os.path.join(root.root, prefix, sub_dir) if prefix else os.path.join(root.root, sub_dir))
                )
            else:
                sub_dir, season_dir, file_name = resolver.get_tv_dest_path(meta, adapter, snapshot)
                parts = [root.root]
                if prefix and not category_in_format:
                    parts.append(prefix)
                if sub_dir:
                    parts.append(sub_dir)
                if season_dir:
                    parts.append(season_dir)
                new_dir = os.path.join(*parts)
            file_name = self._fallback_filename(file_name, old_path)
            if not file_name:
                return None, "empty_filename"
            new_path = os.path.join(new_dir, file_name + ext)
        new_path = os.path.normpath(new_path)
        if not PathUtils.is_path_in_path(root.root, new_path):
            return None, "outside_library_root"
        if len(os.path.dirname(new_path)) > 255 or len(os.path.basename(new_path)) > 255:
            return None, "path_too_long"
        return new_path, None

    @staticmethod
    def _fallback_filename(file_name: str, old_path: str) -> str:
        """模板字段全空时回退到原文件名，避免生成空目录/空文件名."""
        if file_name and re.sub(r"[\W_]+", "", file_name):
            return file_name
        return os.path.splitext(os.path.basename(old_path))[0]

    def _current_category(self, root: LibraryRoot, path: str, media_type: MediaType | None) -> str:
        rel_dir = os.path.relpath(os.path.dirname(path), root.root)
        if rel_dir in (".", ""):
            return ""
        first = rel_dir.replace("\\", "/").split("/")[0]
        if first == RMT_FAVTYPE:
            return first
        return first if first in self._category_names.get((media_type or root.media_type).value, set()) else ""

    def _load_categories(self) -> dict[str, set[str]]:
        result: dict[str, set[str]] = {}
        try:
            for entity in self._category_repo.get_all():
                result.setdefault(entity.media_type, set()).add(entity.name)
        except Exception as e:  # noqa: BLE001
            log.debug(f"[LibraryRename]读取分类失败: {e}")
        return result

    def _mark_conflicts(self, items: list[dict[str, Any]]) -> None:
        targets: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            if item["ACTION"] == "rename" and item.get("NEW_PATH"):
                targets.setdefault(_norm(item["NEW_PATH"]), []).append(item)
        for group in targets.values():
            if len(group) > 1:
                for item in group:
                    item["ACTION"] = "conflict"
                    item["REASON"] = "duplicate_target"

    @staticmethod
    def _excluded(path: str) -> bool:
        normalized = path.replace("\\", "/")
        for segment in normalized.split("/"):
            if not segment:
                continue
            if segment.startswith("."):
                return True
            if segment.lower() in _EXCLUDED_SEGMENTS:
                return True
        return False

    @staticmethod
    def _hash(path: str) -> str:
        return path_hash(_norm(path))


def normalize_backend(backend_id: Any) -> str:
    value = str(backend_id or "local").strip()
    return "local" if value.lower() in ("", "local", "none", "0") else value


def _norm(path: str) -> str:
    return os.path.normpath(str(path or "").replace("\\", "/"))


def _join_format(*parts: str) -> str:
    return "/".join(part for part in parts if part)


def detect_part_hint(name: str) -> bool:
    return bool(re.search(r"(?i)(?:^|[.\s_-])(?:part|cd|disc|disk)[\s._-]*[0-9a-z]+", name))

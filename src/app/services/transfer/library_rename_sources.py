"""批量重命名的元数据候选来源与字段合并."""

from __future__ import annotations

import os
import re
from typing import Any

import log
from app.domain.mediatypes import MediaType
from app.media.models import MediaInfo
from app.media.parser import meta_info
from app.services.transfer.library_rename_models import ResolvedMetadata
from app.storage.backends.base import StorageBackend
from app.utils import JsonUtils, StringUtils

_SEASON_EPISODE_RE = re.compile(r"(?i)S(\d{1,3})(?:\s*-\s*S(\d{1,3}))?[\s._-]*E(\d{1,4})(?:\s*-\s*E?(\d{1,4}))?")
_SEASON_EPISODE_COMPACT_RE = re.compile(r"(?i)S(\d{1,3})E(\d{1,4})E?(\d{1,4})")
_PART_RE = re.compile(r"(?i)(?:^|[.\s_-])((?:part|cd|disc|disk)[\s._-]*[0-9a-z]+)")
_RELEASE_FIELDS = (
    "resource_type",
    "resource_effect",
    "resource_pix",
    "resource_team",
    "customization",
    "video_encode",
    "audio_encode",
)


def from_history(row: dict[str, Any], hint: MediaType) -> ResolvedMetadata | None:
    if not row:
        return None
    media_type = MediaType.from_string(str(row.get("TYPE") or ""))
    if media_type == MediaType.UNKNOWN:
        media_type = hint
    meta = MediaInfo(
        type=media_type,
        title=row.get("TITLE") or None,
        year=row.get("YEAR") or None,
        tmdb_id=_to_int(row.get("TMDBID")),
        category=row.get("CATEGORY") or "",
        content_profile=row.get("CONTENT_PROFILE") or "default",
        anchor_provider=row.get("ANCHOR_PROVIDER"),
        anchor_external_id=row.get("ANCHOR_EXTERNAL_ID"),
        identity_id=row.get("IDENTITY_ID"),
    )
    apply_season_episode(meta, row.get("SEASON_EPISODE") or "")
    source_filename = _basename(row.get("SOURCE_FILENAME") or "")
    return ResolvedMetadata(
        media=meta,
        source="history",
        confidence="high",
        source_filename=source_filename or None,
        history_ids=[int(row["ID"])] if row.get("ID") else [],
    )


def from_cache(row: dict[str, Any], backend: StorageBackend, path: str) -> ResolvedMetadata | None:
    if not row:
        return None
    try:
        stat = backend.stat(path)
    except Exception:  # noqa: BLE001
        return None
    if stat is None:
        return None
    if row.get("FILE_SIZE") is not None and int(row["FILE_SIZE"]) != int(stat.size):
        return None
    if row.get("FILE_MTIME") is not None and abs(float(row["FILE_MTIME"]) - float(stat.mtime)) > 2:
        return None
    media_type = MediaType.from_string(str(row.get("TYPE") or ""))
    if media_type == MediaType.UNKNOWN:
        return None
    raw = {}
    try:
        raw = JsonUtils.loads(row.get("RAW") or "{}")
    except Exception:  # noqa: BLE001
        raw = {}
    meta = MediaInfo(
        type=media_type,
        title=row.get("TITLE") or None,
        year=row.get("YEAR") or None,
        tmdb_id=_to_int(row.get("TMDBID")),
        content_profile=row.get("CONTENT_PROFILE") or raw.get("content_profile") or "default",
        anchor_provider=row.get("ANCHOR_PROVIDER") or raw.get("anchor_provider"),
        anchor_external_id=row.get("ANCHOR_EXTERNAL_ID") or raw.get("anchor_external_id"),
        identity_id=row.get("IDENTITY_ID") or raw.get("identity_id"),
    )
    _apply_range(meta, row.get("SEASON"), row.get("EPISODE"))
    meta.total_episodes = int(row.get("SEASON_EPISODE_COUNT") or 0) or meta.total_episodes
    return ResolvedMetadata(
        media=meta,
        source=str(row.get("METADATA_SOURCE") or "cache"),
        confidence=str(row.get("CONFIDENCE") or "medium"),
        source_filename=row.get("SOURCE_FILENAME") or None,
        is_manual=bool(row.get("IS_MANUAL")),
    )


def from_download_history(entity: Any, base_name: str, hint: MediaType, *, exact: bool) -> ResolvedMetadata | None:
    if not entity:
        return None
    media_type = MediaType.from_string(str(getattr(entity, "media_type", "") or ""))
    if media_type == MediaType.UNKNOWN:
        media_type = hint
    meta = MediaInfo(
        type=media_type,
        title=getattr(entity, "title", None) or None,
        year=getattr(entity, "year", None) or None,
        tmdb_id=_to_int(getattr(entity, "tmdb_id", None)),
        content_profile=getattr(entity, "content_profile", None) or "default",
        anchor_provider=getattr(entity, "anchor_provider", None),
        anchor_external_id=getattr(entity, "anchor_external_id", None),
        identity_id=getattr(entity, "identity_id", None),
    )
    apply_season_episode(meta, getattr(entity, "season_episode", "") or "")
    source_filename = None
    torrent = _basename(getattr(entity, "torrent", "") or "")
    if torrent and (_file_base_matches(torrent, base_name) or (exact and media_type == MediaType.MOVIE)):
        source_filename = torrent
    return ResolvedMetadata(
        media=meta,
        source="download_history",
        confidence="high" if exact else "medium",
        source_filename=source_filename,
    )


def from_nfo(data: dict[str, Any], hint: MediaType) -> ResolvedMetadata | None:
    if not data:
        return None
    media_type = hint
    title = data.get("title")
    tmdbid = _to_int(data.get("tmdbid"))
    season = data.get("season")
    episode = data.get("episode")
    unique_ids = data.get("unique_ids") or {}
    content_id = data.get("content_id") or next(
        (value for key, value in unique_ids.items() if key not in ("tmdb", "imdb") and value),
        None,
    )
    if not title and not tmdbid and not content_id and not (season and episode):
        return None
    meta = MediaInfo(
        type=media_type,
        title=title,
        year=str(data.get("year")) if data.get("year") else None,
        tmdb_id=tmdbid,
        imdb_id=str(data.get("imdbid")) if data.get("imdbid") else "",
        original_title=data.get("original_title"),
        content_profile=str(data.get("content_profile") or "default"),
        anchor_provider="content_id" if content_id else None,
        anchor_external_id=str(content_id) if content_id else None,
    )
    if season is not None:
        meta.begin_season = int(season)
        meta.end_season = int(season)
    if episode is not None:
        meta.begin_episode = int(episode)
        meta.end_episode = int(episode)
    return ResolvedMetadata(
        media=meta,
        source="nfo",
        confidence="high",
        episode_title=data.get("episode_title"),
    )


def from_media_server(item: dict[str, Any], hint: MediaType) -> ResolvedMetadata | None:
    if not item:
        return None
    tmdbid = _to_int(item.get("tmdbid"))
    title = item.get("title")
    if not tmdbid and not title:
        return None
    item_type = str(item.get("type") or "").lower()
    media_type = hint
    if item_type in ("movie",):
        media_type = MediaType.MOVIE
    elif item_type in ("series", "show", "tv"):
        media_type = MediaType.TV
    meta = MediaInfo(
        type=media_type,
        title=title,
        year=str(item.get("year")) if item.get("year") else None,
        tmdb_id=tmdbid,
        imdb_id=str(item.get("imdbid")) if item.get("imdbid") else "",
        original_title=item.get("originalTitle"),
    )
    return ResolvedMetadata(media=meta, source="mediaserver", confidence="high")


def from_filename(path: str, hint: MediaType) -> ResolvedMetadata | None:
    base_name = os.path.basename(path)
    parsed = meta_info(base_name, mtype=hint)
    if not parsed:
        return None
    title = parsed.title or parsed.get_name()
    if not title:
        return None
    parsed.title = title
    parsed.type = hint
    # 当前文件名不是原始下载名，不能作为 original_name/rev_name 来源
    parsed.org_string = None
    parsed.rev_string = None
    return ResolvedMetadata(media=parsed, source="filename", confidence="medium")


def from_online(
    path: str,
    backend: StorageBackend,
    hint: MediaType,
    metadata_gateway: Any,
) -> ResolvedMetadata | None:
    if metadata_gateway is None:
        log.warn(f"[LibraryRename]缺少 MetadataGateway，跳过在线识别: {path}")
        return None
    try:
        result = metadata_gateway.media_info_on_files([path], media_type=hint, backend=backend)
    except Exception as e:  # noqa: BLE001
        log.debug(f"[LibraryRename]在线识别失败 {path}: {e}")
        return None
    if not isinstance(result, dict) or not result:
        return None
    media = next(iter(result.values()), None)
    if not media:
        return None
    title = getattr(media, "title", None) or media.get_name()
    if not title:
        return None
    media.title = title
    media.org_string = None
    media.rev_string = None
    return ResolvedMetadata(media=media, source="online", confidence="medium")


def apply_source(meta: MediaInfo, source_filename: str | None) -> None:
    """从原始下载名补齐发布信息、original_name/rev_name 与 part."""
    if not source_filename:
        return
    source_base = _basename(source_filename)
    if not source_base:
        return
    source_meta = meta_info(source_base, mtype=meta.type)
    for field in _RELEASE_FIELDS:
        if not getattr(meta, field, None) and getattr(source_meta, field, None):
            setattr(meta, field, getattr(source_meta, field))
    if not meta.part:
        meta.part = detect_part(source_base)
    if not meta.org_string:
        meta.org_string = source_base
    if not meta.rev_string:
        meta.rev_string = source_meta.rev_string


def merge_missing(target: MediaInfo, source: MediaInfo) -> None:
    fields = (
        "title",
        "year",
        "tmdb_id",
        "imdb_id",
        "original_title",
        "content_profile",
        "anchor_provider",
        "anchor_external_id",
        "identity_id",
        "begin_season",
        "end_season",
        "begin_episode",
        "end_episode",
        "total_episodes",
        "resource_type",
        "resource_effect",
        "resource_pix",
        "resource_team",
        "customization",
        "video_encode",
        "audio_encode",
        "part",
        "provider_data",
    )
    for field in fields:
        if _empty(getattr(target, field, None)) and not _empty(getattr(source, field, None)):
            setattr(target, field, getattr(source, field))
    if str(getattr(target, "content_profile", "") or "default") == "default":
        source_profile = str(getattr(source, "content_profile", "") or "default")
        if source_profile != "default":
            target.content_profile = source_profile
    if _empty(target.category) and not _empty(source.category):
        target.category = source.category


def finalize_media(meta: MediaInfo, hint: MediaType) -> None:
    if not meta.type or meta.type == MediaType.UNKNOWN:
        meta.type = hint
    if meta.title and not meta.cn_name and not meta.en_name:
        if StringUtils.is_all_chinese(meta.title):
            meta.cn_name = meta.title
        else:
            meta.en_name = meta.title
    if meta.part is None:
        meta.part = detect_part(meta.org_string or "")


def apply_online(
    resolved: ResolvedMetadata,
    metadata_gateway: Any,
) -> None:
    if metadata_gateway is None:
        log.warn("[LibraryRename]缺少 MetadataGateway，跳过在线元数据补全")
        return
    meta = resolved.media
    tmdbid = _to_int(meta.tmdb_id)
    if not tmdbid or not meta.type or meta.type == MediaType.UNKNOWN:
        return
    try:
        info = metadata_gateway.details_for_media(meta, append_to_response="all")
        if info:
            meta.set_provider_data(info)
    except Exception as e:  # noqa: BLE001
        log.debug(f"[LibraryRename]补全 TMDB 信息失败 {tmdbid}: {e}")
        return
    if meta.original_title:
        resolved.online_fields.append("original_title")
    if meta.imdb_id:
        resolved.online_fields.append("imdbid")
    if (
        meta.type in (MediaType.TV, MediaType.ANIME)
        and meta.begin_season is not None
        and meta.begin_episode is not None
    ):
        try:
            episode_title = metadata_gateway.episode_title(meta)
            if episode_title:
                resolved.episode_title = episode_title
                resolved.online_fields.append("episode_title")
        except Exception as e:  # noqa: BLE001
            log.debug(f"[LibraryRename]获取集标题失败: {e}")
    try:
        en_title = metadata_gateway.en_title(meta)
        if en_title:
            resolved.en_title = en_title
            resolved.online_fields.append("en_title")
    except Exception as e:  # noqa: BLE001
        log.debug(f"[LibraryRename]获取英文标题失败: {e}")


def apply_season_episode(meta: MediaInfo, text: str) -> None:
    compact = _SEASON_EPISODE_COMPACT_RE.search(text or "")
    if compact:
        begin_season = int(compact.group(1))
        end_season = begin_season
        begin_episode = int(compact.group(2))
        end_episode = int(compact.group(3)) if compact.group(3) else begin_episode
    else:
        match = _SEASON_EPISODE_RE.search(text or "")
        if not match:
            return
        begin_season = int(match.group(1))
        end_season = int(match.group(2)) if match.group(2) else begin_season
        begin_episode = int(match.group(3))
        end_episode = int(match.group(4)) if match.group(4) else begin_episode
    meta.begin_season = begin_season
    meta.end_season = end_season
    meta.begin_episode = begin_episode
    meta.end_episode = end_episode


def parse_season_episode(text: str) -> tuple[int | None, int | None, int | None, int | None]:
    meta = MediaInfo()
    apply_season_episode(meta, text)
    return meta.begin_season, meta.end_season, meta.begin_episode, meta.end_episode


def detect_part(name: str) -> str | None:
    if not name:
        return None
    match = _PART_RE.search(name)
    return re.sub(r"[._-]+", " ", match.group(1)).strip() if match else None


def _apply_range(meta: MediaInfo, season: Any, episode: Any) -> None:
    if season is not None and str(season).strip() != "":
        begin, _, end, _ = _split_range(str(season))
        meta.begin_season = begin
        meta.end_season = end if end is not None else begin
    if episode is not None and str(episode).strip() != "":
        begin, _, end, _ = _split_range(str(episode))
        meta.begin_episode = begin
        meta.end_episode = end if end is not None else begin


def _split_range(value: str) -> tuple[int | None, int | None, int | None, int | None]:
    parts = re.split(r"\s*-\s*", value.strip(), maxsplit=1)
    try:
        begin = int(parts[0])
        end = int(parts[1]) if len(parts) > 1 else None
    except ValueError:
        return None, None, None, None
    return begin, None, end, None


def _file_base_matches(source_name: str, current_name: str) -> bool:
    source = os.path.splitext(source_name)[0].lower()
    current = os.path.splitext(current_name)[0].lower()
    return bool(source and current and (source == current or source.startswith(current) or current.startswith(source)))


def _basename(value: str) -> str:
    return os.path.basename(str(value or "").replace("\\", "/")).strip()


def _to_int(value: Any) -> int:
    try:
        return int(str(value).strip()) if value is not None and str(value).strip().isdigit() else 0
    except (TypeError, ValueError):
        return 0


def _empty(value: Any) -> bool:
    return value is None or value == "" or value == 0 or value == {}

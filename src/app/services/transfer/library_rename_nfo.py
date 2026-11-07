"""媒体库 NFO 读取与字段合并."""

from __future__ import annotations

import os
import re
from typing import Any

import defusedxml.ElementTree as ET  # type: ignore[import-untyped]

import log
from app.domain.media_types import ProviderMediaType
from app.storage.backends.base import StorageBackend

_MAX_NFO_SIZE = 2 * 1024 * 1024
_NFO_KNOWN_NAMES = {"movie.nfo", "tvshow.nfo", "season.nfo"}


def read_nfo(backend: StorageBackend, path: str) -> dict[str, Any] | None:
    """读取并解析单个 NFO；失败返回 None."""
    try:
        info = backend.stat(path)
        if info is None or info.is_dir or info.size > _MAX_NFO_SIZE:
            return None
        stream = backend.read_stream(path)
        try:
            content = stream.read()
        finally:
            stream.close()
        root = ET.fromstring(content)
    except Exception as e:  # noqa: BLE001
        log.debug(f"[LibraryRename]读取 NFO 失败 {path}: {e}")
        return None
    return _parse_root(root, path)


def _parse_root(root, path: str) -> dict[str, Any]:
    kind = str(root.tag or "").strip().lower()
    data: dict[str, Any] = {"kind": kind, "path": path}
    if kind in ("movie", "tvshow"):
        data.update(
            {
                "title": _text(root, "title"),
                "year": _year(root),
                "tmdbid": _unique_id(root, "tmdb") or _text(root, "tmdbid"),
                "imdbid": _unique_id(root, "imdb") or _text(root, "imdbid"),
                "content_id": _unique_id(root, "content_id"),
                "unique_ids": _unique_ids(root),
                "original_title": _text(root, "originaltitle"),
            }
        )
    elif kind == "episodedetails":
        data.update(
            {
                "episode_title": _text(root, "title"),
                "season": _int_text(root, "season"),
                "episode": _int_text(root, "episode"),
                # tmdbid 是单集 ID，绝不能当剧集 ID 使用
            }
        )
    elif kind == "season":
        data.update({"season": _int_text(root, "seasonnumber") or _int_text(root, "season")})
    return data


def collect_nfo(
    backend: StorageBackend,
    directory: str,
    base_name: str,
    media_type: ProviderMediaType,
) -> dict[str, Any] | None:
    """按 ADR 约定查找并合并 NFO 字段."""
    if media_type == ProviderMediaType.MOVIE:
        return _collect_movie(backend, directory, base_name)
    return _collect_tv(backend, directory, base_name)


def _collect_movie(backend: StorageBackend, directory: str, base_name: str) -> dict[str, Any] | None:
    candidates = [os.path.join(directory, "movie.nfo"), os.path.join(directory, f"{base_name}.nfo")]
    merged: dict[str, Any] = {}
    for path in candidates:
        data = read_nfo(backend, path)
        if data and data.get("kind") == "movie":
            _merge_missing(merged, data)
    return merged or None


def _collect_tv(backend: StorageBackend, directory: str, base_name: str) -> dict[str, Any] | None:
    merged: dict[str, Any] = {}
    episode_path = os.path.join(directory, f"{base_name}.nfo")
    episode = read_nfo(backend, episode_path)
    if not episode:
        episode = _find_episode_nfo(backend, directory, base_name)
    if episode and episode.get("kind") == "episodedetails":
        _merge_missing(merged, episode)

    season = read_nfo(backend, os.path.join(directory, "season.nfo"))
    if season and season.get("kind") == "season":
        # season.nfo 只提供季号，不提供剧集身份
        merged.setdefault("season", season.get("season"))

    show = read_nfo(backend, os.path.join(directory, "tvshow.nfo"))
    if not show:
        parent = os.path.dirname(directory)
        show = read_nfo(backend, os.path.join(parent, "tvshow.nfo"))
    if show and show.get("kind") == "tvshow":
        # 身份字段以 tvshow 为准
        for key in ("title", "year", "tmdbid", "imdbid", "content_id", "unique_ids", "original_title"):
            if show.get(key):
                merged[key] = show[key]
        merged["show_path"] = show.get("path")
    return merged or None


def _find_episode_nfo(backend: StorageBackend, directory: str, base_name: str) -> dict[str, Any] | None:
    """同目录基名不匹配时，用 season/episode 唯一匹配其他 NFO."""
    expected = _episode_from_name(base_name)
    if not expected:
        return None
    matches: list[dict[str, Any]] = []
    try:
        for info in backend.list_dir(directory):
            if info.is_dir:
                continue
            name = os.path.basename(info.path)
            if not name.lower().endswith(".nfo") or name.lower() in _NFO_KNOWN_NAMES:
                continue
            data = read_nfo(backend, info.path)
            if not data or data.get("kind") != "episodedetails":
                continue
            if str(data.get("season")) == expected[0] and str(data.get("episode")) == expected[1]:
                matches.append(data)
    except Exception as e:  # noqa: BLE001
        log.debug(f"[LibraryRename]扫描同目录 NFO 失败 {directory}: {e}")
    return matches[0] if len(matches) == 1 else None


def _episode_from_name(base_name: str) -> tuple[str, str] | None:
    match = re.search(r"(?i)s(\d{1,3})[\s._-]*e(\d{1,4})", base_name)
    if not match:
        return None
    return str(int(match.group(1))), str(int(match.group(2)))


def _merge_missing(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if key in ("kind", "path"):
            continue
        if value is not None and value != "" and not target.get(key):
            target[key] = value


def _text(root, name: str) -> str | None:
    elem = root.find(name)
    text = (elem.text or "").strip() if elem is not None else ""
    return text or None


def _int_text(root, name: str) -> int | None:
    text = _text(root, name)
    if not text:
        return None
    try:
        value = int(text)
    except ValueError:
        return None
    return value if value >= 0 else None


def _year(root) -> str | None:
    year = _text(root, "year")
    if year:
        return year[:4]
    premiered = _text(root, "premiered")
    return premiered[:4] if premiered else None


def _unique_ids(root) -> dict[str, str]:
    result = {}
    for elem in root.findall("uniqueid"):
        id_type = str(elem.get("type") or "").strip().lower()
        text = (elem.text or "").strip()
        if id_type and text:
            result[id_type] = text
    return result


def _unique_id(root, id_type: str) -> str | None:
    for elem in root.findall("uniqueid"):
        if str(elem.get("type") or "").strip().lower() == id_type:
            text = (elem.text or "").strip()
            if text:
                return text
    return None

"""订阅上下文解析：消息层不再直接依赖订阅仓储."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.domain.mediatypes import MediaType
from app.services.subscribe_repo_adapter import (
    SubscribeMovieRepositoryAdapter,
    SubscribeTvRepositoryAdapter,
)


def _value(row: Any, *names: str):
    for name in names:
        value = getattr(row, name, None)
        if value is not None:
            return value
    return None


def _is_tv(item: Any) -> bool:
    value = getattr(item, "type", None)
    if value in (MediaType.TV, MediaType.ANIME):
        return True
    return str(value or "").lower() in {"tv", "anime", "show", "series"}


def _context(row: Any, media_type: MediaType) -> SimpleNamespace:
    return SimpleNamespace(
        id=_value(row, "ID", "id"),
        name=_value(row, "NAME", "name") or "",
        year=_value(row, "YEAR", "year") or "",
        season=_value(row, "SEASON", "season") or "",
        image=_value(row, "IMAGE", "image") or "",
        tmdbid=_value(row, "TMDBID", "tmdbid") or "",
        identity_id=_value(row, "IDENTITY_ID", "identity_id"),
        anchor_provider=_value(row, "ANCHOR_PROVIDER", "anchor_provider"),
        anchor_external_id=_value(row, "ANCHOR_EXTERNAL_ID", "anchor_external_id"),
        content_profile=_value(row, "CONTENT_PROFILE", "content_profile"),
        provider=_value(row, "PROVIDER", "provider"),
        metadata_ref=_value(row, "METADATA_REF", "metadata_ref"),
        metadata_policy=_value(row, "METADATA_POLICY", "metadata_policy"),
        naming_profile=_value(row, "NAMING_PROFILE", "naming_profile"),
        keyword=_value(row, "KEYWORD", "keyword"),
        filter_restype=_value(row, "FILTER_RESTYPE", "filter_restype"),
        filter_pix=_value(row, "FILTER_PIX", "filter_pix"),
        filter_team=_value(row, "FILTER_TEAM", "filter_team"),
        filter_rule=_value(row, "FILTER_RULE", "filter_rule"),
        filter_include=_value(row, "FILTER_INCLUDE", "filter_include"),
        filter_exclude=_value(row, "FILTER_EXCLUDE", "filter_exclude"),
        filter_free=_value(row, "FILTER_FREE", "filter_free"),
        desc=_value(row, "DESC", "desc") or "",
        type=media_type,
    )


def resolve_subscription_context(item: Any):
    """按 rssid → identity/anchor → tmdb → 标题+年份 查找订阅上下文."""
    media_type = MediaType.TV if _is_tv(item) else MediaType.MOVIE
    repo = SubscribeTvRepositoryAdapter() if media_type == MediaType.TV else SubscribeMovieRepositoryAdapter()
    try:
        rssid = getattr(item, "rssid", None)
        rows = repo.get_all(rssid=int(rssid)) if rssid else []
        if rows:
            return _context(rows[0], media_type)

        identity_id = str(getattr(item, "identity_id", "") or "").strip()
        provider = str(getattr(item, "anchor_provider", "") or "").strip()
        external = str(getattr(item, "anchor_external_id", "") or "").strip()
        tmdbid = str(getattr(item, "tmdb_id", "") or "").strip()
        title = str(getattr(item, "title", "") or "").strip()
        year = str(getattr(item, "year", "") or "").strip()
        for row in repo.get_all():
            row_identity = str(_value(row, "IDENTITY_ID", "identity_id") or "").strip()
            row_provider = str(_value(row, "ANCHOR_PROVIDER", "anchor_provider") or "").strip()
            row_external = str(_value(row, "ANCHOR_EXTERNAL_ID", "anchor_external_id") or "").strip()
            if identity_id and row_identity == identity_id:
                return _context(row, media_type)
            if provider and external and (row_provider, row_external) == (provider, external):
                return _context(row, media_type)
            if tmdbid and str(_value(row, "TMDBID", "tmdbid") or "") == tmdbid:
                return _context(row, media_type)
            row_name = str(_value(row, "NAME", "name") or "").strip()
            row_year = str(_value(row, "YEAR", "year") or "").strip()
            if title and row_name == title and (not year or row_year == year):
                return _context(row, media_type)
    except Exception:  # noqa: BLE001
        return None
    return None

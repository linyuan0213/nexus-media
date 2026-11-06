"""手动转移 TMDB 类型解析（实时查询 + 类型选错回退）测试."""

from typing import Any, cast
from unittest.mock import MagicMock

from app.domain.mediatypes import MediaType
from app.services.sync_service import SyncService


def _svc(results, media_service=True):
    svc = SyncService.__new__(SyncService)
    gateway = MagicMock()
    gateway.details.side_effect = results
    setattr(svc, "_metadata_gateway", gateway)
    if media_service:
        ms = MagicMock()
        setattr(svc, "_media_service", ms)
    else:
        setattr(svc, "_media_service", None)
    cache = MagicMock()
    setattr(svc, "_media_cache", cache)
    return svc, cache


def test_primary_type_hit():
    svc, _cache = _svc([{"id": 1, "title": "电影", "media_type": "movie"}])
    info, mtype = svc._resolve_manual_tmdb_info(MediaType.MOVIE, 1)
    assert info and mtype == MediaType.MOVIE
    assert cast(Any, svc._metadata_gateway).details.call_count == 1


def test_falls_back_to_tv_when_movie_miss():
    """电视剧 id 按电影查不到时回退 tv，并纠正类型（否则报“无法查询到TMDB信息”）."""
    svc, _cache = _svc([None, {"id": 2, "name": "剧集", "media_type": "tv"}])
    info, mtype = svc._resolve_manual_tmdb_info(MediaType.MOVIE, 2)
    assert info and mtype == MediaType.TV


def test_falls_back_to_movie_when_tv_miss():
    svc, _cache = _svc([None, {"id": 3, "title": "电影", "media_type": "movie"}])
    info, mtype = svc._resolve_manual_tmdb_info(MediaType.TV, 3)
    assert info and mtype == MediaType.MOVIE


def test_both_miss_returns_none():
    svc, _cache = _svc([None, None])
    info, mtype = svc._resolve_manual_tmdb_info(MediaType.MOVIE, 4)
    assert info is None and mtype == MediaType.MOVIE


def test_type_corrected_from_detail_media_type():
    """即使首个类型查询有返回，也以详情 media_type 为准纠正（动漫按 tv 查询等）."""
    svc, _cache = _svc([{"id": 5, "title": "电影", "media_type": "movie"}])
    info, mtype = svc._resolve_manual_tmdb_info(MediaType.TV, 5)
    assert info and mtype == MediaType.MOVIE


def test_live_fetch_used_even_without_cache():
    """缓存未命中也能实时查询（#170：搜索能拿到 ID 但转移报查询不到 TMDB）."""
    svc, cache = _svc([{"id": 6, "title": "电影", "media_type": "movie"}])
    info, _mtype = svc._resolve_manual_tmdb_info(MediaType.MOVIE, 6)
    assert info is not None
    cache.get_tmdb_info.assert_not_called()


def test_uses_gateway_even_without_media_service():
    svc, cache = _svc([{"id": 7, "title": "电影", "media_type": "movie"}], media_service=False)
    info, mtype = svc._resolve_manual_tmdb_info(MediaType.MOVIE, 7)
    assert info and mtype == MediaType.MOVIE
    cache.get_tmdb_info.assert_not_called()
    assert cast(Any, svc._metadata_gateway).details.call_count == 1


def test_provider_payload_is_injected_from_plugin():
    svc = SyncService.__new__(SyncService)
    metadata = MagicMock()
    metadata.lookup.return_value = {
        "title": "示例番号",
        "year": "2026",
        "media_type": "movie",
        "content_profile": "custom",
        "overview": "简介",
        "images": {"poster": [{"url": "https://example.com/poster.jpg"}]},
        "genres": ["剧情"],
    }
    setattr(svc, "_metadata_gateway", metadata)

    payload, mtype = svc._resolve_manual_provider_info(MediaType.MOVIE, "custom", "demo", "ABC-001")

    assert mtype == MediaType.MOVIE
    assert payload is not None
    assert payload["content_profile"] == "custom"
    assert payload["anchor_provider"] == "demo"
    assert payload["anchor_external_id"] == "ABC-001"
    assert payload["provider"] == "demo"
    assert payload["title"] == "示例番号"
    assert payload["poster_path"] == "https://example.com/poster.jpg"
    args, kwargs = metadata.lookup.call_args
    assert args == ("demo", "ABC-001")
    assert kwargs["media_type"] == MediaType.MOVIE
    assert kwargs["content_profile"] == "custom"
    assert kwargs["context"].allow_private is False


def test_provider_payload_missing_returns_none():
    svc = SyncService.__new__(SyncService)
    metadata = MagicMock()
    metadata.lookup.return_value = None
    setattr(svc, "_metadata_gateway", metadata)

    payload, mtype = svc._resolve_manual_provider_info(MediaType.MOVIE, "custom", "demo", "ABC-001")

    assert payload is None
    assert mtype == MediaType.MOVIE

"""手动转移 TMDB 类型解析（类型选错回退）测试."""

from unittest.mock import MagicMock

from app.domain.mediatypes import MediaType
from app.services.sync_service import SyncService


def _svc(results):
    svc = SyncService.__new__(SyncService)
    cache = MagicMock()
    cache.get_tmdb_info.side_effect = results
    setattr(svc, "_media_cache", cache)
    return svc, cache


def test_primary_type_hit():
    svc, cache = _svc([{"id": 1, "title": "电影"}])
    info, mtype = svc._resolve_manual_tmdb_info(MediaType.MOVIE, 1)
    assert info and mtype == MediaType.MOVIE
    assert cache.get_tmdb_info.call_count == 1


def test_falls_back_to_tv_when_movie_miss():
    """电视剧 id 按电影查不到时回退 tv，并纠正类型（否则报“无法查询到TMDB信息”）."""
    svc, _cache = _svc([None, {"id": 2, "name": "剧集"}])
    info, mtype = svc._resolve_manual_tmdb_info(MediaType.MOVIE, 2)
    assert info and mtype == MediaType.TV


def test_falls_back_to_movie_when_tv_miss():
    svc, _cache = _svc([None, {"id": 3, "title": "电影"}])
    info, mtype = svc._resolve_manual_tmdb_info(MediaType.TV, 3)
    assert info and mtype == MediaType.MOVIE


def test_both_miss_returns_none():
    svc, _cache = _svc([None, None])
    info, mtype = svc._resolve_manual_tmdb_info(MediaType.MOVIE, 4)
    assert info is None and mtype == MediaType.MOVIE

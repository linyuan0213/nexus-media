"""BaseSearchStrategy 单元测试."""

from unittest.mock import MagicMock, patch

import pytest

from app.domain.mediatypes import MediaType
from app.services.subscribe.strategies.base_search import BaseSearchStrategy


class _MediaInfo:
    def __init__(self):
        self.tmdb_info = {"id": 123}
        self.tmdb_id = 123
        self.title = "Test"
        self.type = "movie"
        self.keyword = None
        self.over_edition = None
        self.res_order = None
        self.begin_season = None
        self.rssid = None

    def set_download_info(self, **kwargs):
        pass

    def set_tmdb_info(self, info):
        self.tmdb_info = info

    def get_title_string(self):
        return self.title

    def get_poster_image(self):
        return "http://poster.jpg"


@pytest.fixture
def strategy():
    s = BaseSearchStrategy(
        service=MagicMock(),
        searcher=MagicMock(),
        media_service=MagicMock(),
        media_cache=MagicMock(),
        downloader=MagicMock(),
        filter_service=MagicMock(),
        message=MagicMock(),
    )
    s._ident_cache.clear()
    return s


class TestBaseSearchStrategy:
    def test_set_coordinator(self, strategy):
        coord = MagicMock()
        strategy.set_coordinator(coord)
        assert strategy._coordinator is coord

    def test_search_movies_fuzzy_match(self, strategy):
        strategy._service.get_subscribe_movies.return_value = {"1": {"id": 1, "fuzzy_match": True}}
        strategy._movie_repo = MagicMock()
        strategy._search_movies()
        strategy._movie_repo.update_state.assert_not_called()

    def test_search_movies_tmdb_fail(self, strategy):
        strategy._service.get_subscribe_movies.return_value = {"1": {"id": 1, "name": "Movie"}}
        strategy._movie_repo = MagicMock()
        with patch.object(strategy, "_get_media_info", return_value=None):
            strategy._search_movies()
        strategy._movie_repo.update_state.assert_called_with(title=None, year=None, rssid=1, state="E")

    def test_search_movies_already_exists(self, strategy):
        strategy._service.get_subscribe_movies.return_value = {"1": {"id": 1, "name": "Movie"}}
        strategy._movie_repo = MagicMock()
        media = _MediaInfo()
        strategy._downloader.check_exists_medias.return_value = (True, {}, None)
        with patch.object(strategy, "_get_media_info", return_value=media):
            strategy._search_movies()
        strategy._service.finish_rss_subscribe.assert_called_once()

    def test_search_movies_found(self, strategy):
        strategy._service.get_subscribe_movies.return_value = {"1": {"id": 1, "name": "Movie"}}
        strategy._movie_repo = MagicMock()
        media = _MediaInfo()
        result = _MediaInfo()
        result.type = "movie"
        strategy._searcher.search_one_media.return_value = (result, None, None, None)
        strategy._downloader.check_exists_medias.return_value = (False, {}, None)
        with patch.object(strategy, "_get_media_info", return_value=media):
            strategy._search_movies()
        strategy._service.finish_rss_subscribe.assert_called_once()

    def test_search_movies_not_found(self, strategy):
        strategy._service.get_subscribe_movies.return_value = {"1": {"id": 1, "name": "Movie"}}
        strategy._movie_repo = MagicMock()
        media = _MediaInfo()
        strategy._searcher.search_one_media.return_value = (None, None, None, None)
        strategy._downloader.check_exists_medias.return_value = (False, {}, None)
        with patch.object(strategy, "_get_media_info", return_value=media):
            strategy._search_movies()
        strategy._movie_repo.update_state.assert_called_with(title=None, year=None, rssid=1, state="R")

    def test_search_tvs_tmdb_fail(self, strategy):
        strategy._service.get_subscribe_tvs.return_value = {"1": {"id": 1, "name": "TV"}}
        strategy._tv_repo = MagicMock()
        strategy._tv_episode_repo = MagicMock()
        with patch.object(strategy, "_get_media_info", return_value=None):
            strategy._search_tvs()
        strategy._tv_repo.update_state.assert_called_with(title=None, year=None, season=None, rssid=1, state="E")

    def test_search_tvs_all_exist(self, strategy):
        strategy._service.get_subscribe_tvs.return_value = {"1": {"id": 1, "name": "TV", "season": 1, "total": 10}}
        strategy._tv_repo = MagicMock()
        strategy._tv_episode_repo = MagicMock()
        media = _MediaInfo()
        media.type = "tv"
        strategy._downloader.check_exists_medias.return_value = (True, {}, None)
        strategy._tv_episode_repo.get.return_value = None
        with patch.object(strategy, "_get_media_info", return_value=media):
            strategy._search_tvs()
        strategy._service.finish_rss_subscribe.assert_called_once()

    def test_get_media_info_with_tmdbid(self, strategy):
        media = _MediaInfo()
        strategy._media_cache.get_tmdb_info.return_value = {"id": 123}
        with patch("app.services.subscribe.strategies.base_search.meta_info") as mock_meta:
            mock_meta.return_value = media
            result = strategy._get_media_info(123, "Name", "2024", MediaType.MOVIE)
            assert result is media

    def test_get_media_info_without_tmdbid(self, strategy):
        media = _MediaInfo()
        strategy._media_service.identify.return_value = media
        result = strategy._get_media_info(None, "Name", "2024", MediaType.MOVIE)
        assert result is media
        # 第二次调用应走缓存，identify 只调用一次
        result2 = strategy._get_media_info(None, "Name", "2024", MediaType.MOVIE)
        assert result2 is media
        strategy._media_service.identify.assert_called_once()

    def test_get_media_info_with_tmdbid_caches(self, strategy):
        media = _MediaInfo()
        strategy._media_cache.get_tmdb_info.return_value = {"id": 123}
        with patch("app.services.subscribe.strategies.base_search.meta_info") as mock_meta:
            mock_meta.return_value = media
            result = strategy._get_media_info(123, "Name", "2024", MediaType.MOVIE)
            assert result.tmdb_id == media.tmdb_id
            strategy._media_cache.get_tmdb_info.assert_called_once()
            result2 = strategy._get_media_info(123, "Name", "2024", MediaType.MOVIE)
            assert result2.tmdb_id == media.tmdb_id

    def test_get_media_info_different_keys_not_shared(self, strategy):
        media1 = _MediaInfo()
        media2 = _MediaInfo()
        media2.tmdb_id = 456
        strategy._media_service.identify.side_effect = [media1, media2]
        r1 = strategy._get_media_info(None, "Name1", "2024", MediaType.MOVIE)
        r2 = strategy._get_media_info(None, "Name2", "2024", MediaType.MOVIE)
        assert r1 is media1
        assert r2 is media2
        assert strategy._media_service.identify.call_count == 2

    def test_get_media_info_douban_prefix(self, strategy):
        media = _MediaInfo()
        strategy._media_service.identify.return_value = media
        result = strategy._get_media_info("DB:123", "Name", "2024", MediaType.MOVIE)
        assert result is media

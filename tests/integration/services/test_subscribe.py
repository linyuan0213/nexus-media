"""Tests for app.services.subscribe package."""

from unittest.mock import MagicMock


from app.services.subscribe.query_service import SubscribeQueryService
from app.services.subscribe.utils import gen_rss_note, parse_rss_desc


class TestSubscribeUtils:
    """Test suite for subscribe utility functions."""

    def test_parse_rss_desc_empty(self):
        assert parse_rss_desc(None) == {}
        assert parse_rss_desc("") == {}

    def test_parse_rss_desc_valid(self):
        assert parse_rss_desc('{"a": 1}') == {"a": 1}

    def test_gen_rss_note_empty(self):
        assert gen_rss_note(None) == "{}"

    def test_gen_rss_note_populated(self):
        media = MagicMock()
        media.get_poster_image.return_value = "http://poster.jpg"
        media.release_date = "2024-01-01"
        media.vote_average = 8.5
        result = gen_rss_note(media)
        assert "http://poster.jpg" in result
        assert "2024-01-01" in result


class TestSubscribeQueryService:
    """Test suite for SubscribeQueryService."""

    def test_get_subscribe_movies_empty(self):
        movie_repo = MagicMock()
        movie_repo.get_all.return_value = []
        sites = MagicMock()
        sites.get_site_names.return_value = []
        indexer = MagicMock()
        indexer.get_user_indexer_names.return_value = []
        svc = SubscribeQueryService(movie_repo, MagicMock(), MagicMock(), MagicMock(), sites, indexer)
        result = svc.get_subscribe_movies()
        assert result == {}

    def test_get_subscribe_tvs_empty(self):
        tv_repo = MagicMock()
        tv_repo.get_all.return_value = []
        sites = MagicMock()
        sites.get_site_names.return_value = []
        indexer = MagicMock()
        indexer.get_user_indexer_names.return_value = []
        svc = SubscribeQueryService(MagicMock(), tv_repo, MagicMock(), MagicMock(), sites, indexer)
        result = svc.get_subscribe_tvs()
        assert result == {}

    def test_get_subscribe_tv_episodes(self):
        episode_repo = MagicMock()
        episode_repo.get.return_value = [1, 2, 3]
        svc = SubscribeQueryService(MagicMock(), MagicMock(), episode_repo, MagicMock(), MagicMock(), MagicMock())
        result = svc.get_subscribe_tv_episodes(1)
        assert result == [1, 2, 3]

    def test_check_history(self):
        history_repo = MagicMock()
        history_repo.check_exists.return_value = True
        svc = SubscribeQueryService(MagicMock(), MagicMock(), MagicMock(), history_repo, MagicMock(), MagicMock())
        assert svc.check_history("MOV", "Test", "2024", None) is True
        history_repo.check_exists.assert_called_once_with(type_str="MOV", name="Test", year="2024", season="")

    def test_delete_subscribe_movie(self):
        movie_repo = MagicMock()
        movie_repo.delete.return_value = True
        svc = SubscribeQueryService(movie_repo, MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock())
        from app.utils.types import MediaType

        svc.delete_subscribe(MediaType.MOVIE, rssid=1)
        movie_repo.delete.assert_called_once_with(title=None, year=None, rssid=1, tmdbid=None)

    def test_delete_subscribe_tv(self):
        tv_repo = MagicMock()
        tv_repo.delete.return_value = True
        svc = SubscribeQueryService(MagicMock(), tv_repo, MagicMock(), MagicMock(), MagicMock(), MagicMock())
        from app.utils.types import MediaType

        svc.delete_subscribe(MediaType.TV, rssid=1)
        tv_repo.delete.assert_called_once_with(title=None, season=None, rssid=1, tmdbid=None)

    def test_get_subscribe_id_movie(self):
        movie_repo = MagicMock()
        movie_repo.get_id.return_value = 42
        svc = SubscribeQueryService(movie_repo, MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock())
        from app.utils.types import MediaType

        result = svc.get_subscribe_id(MediaType.MOVIE, "Test")
        assert result == 42

    def test_get_subscribe_id_tv(self):
        tv_repo = MagicMock()
        tv_repo.get_id.return_value = 42
        svc = SubscribeQueryService(MagicMock(), tv_repo, MagicMock(), MagicMock(), MagicMock(), MagicMock())
        from app.utils.types import MediaType

        result = svc.get_subscribe_id(MediaType.TV, "Test")
        assert result == 42

    def test_get_subscribe_movies_with_legacy_desc(self):
        movie_repo = MagicMock()
        rss = MagicMock()
        rss.ID = 1
        rss.NAME = "Test"
        rss.YEAR = "2024"
        rss.TMDBID = "123"
        rss.IMAGE = "img.jpg"
        rss.DESC = '{"rss_sites": ["site1"], "over_edition": "Y"}'
        rss.NOTE = None
        rss.RSS_SITES = None
        rss.SEARCH_SITES = None
        rss.OVER_EDITION = 0
        rss.FILTER_RESTYPE = None
        rss.FILTER_PIX = None
        rss.FILTER_TEAM = None
        rss.FILTER_RULE = None
        rss.FILTER_INCLUDE = None
        rss.FILTER_EXCLUDE = None
        rss.DOWNLOAD_SETTING = None
        rss.SAVE_PATH = None
        rss.FUZZY_MATCH = 0
        rss.KEYWORD = None
        movie_repo.get_all.return_value = [rss]
        sites = MagicMock()
        sites.get_site_names.return_value = ["site1"]
        indexer = MagicMock()
        indexer.get_user_indexer_names.return_value = []
        svc = SubscribeQueryService(movie_repo, MagicMock(), MagicMock(), MagicMock(), sites, indexer)
        result = svc.get_subscribe_movies()
        assert "1" in result
        assert result["1"]["over_edition"] is True

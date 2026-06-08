"""Tests for app.services.subscribe package."""

from unittest.mock import MagicMock, patch

from app.services.subscribe.management.calendar_service import SubscribeCalendarService
from app.services.subscribe.management.history_service import SubscribeHistoryService
from app.services.subscribe.management.query_service import SubscribeQueryService
from app.services.subscribe.management.utils import gen_rss_note, parse_rss_desc
from app.services.subscribe.matcher import SubscribeMatcher
from app.services.subscribe.monitor import SubscriptionMonitor
from app.domain.mediatypes import MediaType


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
        from app.domain.mediatypes import MediaType

        svc.delete_subscribe(MediaType.MOVIE, rssid=1)
        movie_repo.delete.assert_called_once_with(title=None, year=None, rssid=1, tmdbid=None)

    def test_delete_subscribe_tv(self):
        tv_repo = MagicMock()
        tv_repo.delete.return_value = True
        svc = SubscribeQueryService(MagicMock(), tv_repo, MagicMock(), MagicMock(), MagicMock(), MagicMock())
        from app.domain.mediatypes import MediaType

        svc.delete_subscribe(MediaType.TV, rssid=1)
        tv_repo.delete.assert_called_once_with(title=None, season=None, rssid=1, tmdbid=None)

    def test_get_subscribe_id_movie(self):
        movie_repo = MagicMock()
        movie_repo.get_id.return_value = 42
        svc = SubscribeQueryService(movie_repo, MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock())
        from app.domain.mediatypes import MediaType

        result = svc.get_subscribe_id(MediaType.MOVIE, "Test")
        assert result == 42

    def test_get_subscribe_id_tv(self):
        tv_repo = MagicMock()
        tv_repo.get_id.return_value = 42
        svc = SubscribeQueryService(MagicMock(), tv_repo, MagicMock(), MagicMock(), MagicMock(), MagicMock())
        from app.domain.mediatypes import MediaType

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


class TestSubscribeMatcher:
    """Test suite for SubscribeMatcher."""

    def _make_media(self, mtype=MediaType.MOVIE, tmdb_id="123", title="Test", year="2024", site="site1"):
        media = MagicMock()
        media.type = mtype
        media.tmdb_id = tmdb_id
        media.title = title
        media.year = year
        media.site = site
        media.org_string = "Test.2024.1080p"
        media.rev_string = "Test"
        media.get_title_string.return_value = title
        media.get_season_episode_string.return_value = ""
        media.get_season_string.return_value = "S01"
        media.subtitle = "subtitle"
        media.page_url = "http://test"
        return media

    def test_movie_no_match_empty_movies(self):
        matcher = SubscribeMatcher()
        media = self._make_media()
        flag, msgs, info = matcher.match(media, {}, {}, None, None, None, False, None, None, None)
        assert flag is False
        assert len(msgs) == 1
        assert "不在订阅范围" in msgs[0]

    def test_movie_match_by_tmdbid(self):
        matcher = SubscribeMatcher()
        media = self._make_media(tmdb_id="123")
        rss_movies = {"1": {"name": "Test", "year": "2024", "tmdbid": "123", "fuzzy_match": False}}
        filter_engine = MagicMock()
        filter_engine.check_torrent_filter.return_value = (True, 1, "ok")
        matcher._filter = filter_engine
        flag, msgs, info = matcher.match(media, rss_movies, {}, None, None, None, False, None, None, None)
        assert flag is True
        assert info["tmdbid"] == "123"

    def test_movie_no_match_wrong_tmdbid(self):
        matcher = SubscribeMatcher()
        media = self._make_media(tmdb_id="999")
        rss_movies = {"1": {"name": "Test", "year": "2024", "tmdbid": "123", "fuzzy_match": False}}
        flag, msgs, info = matcher.match(media, rss_movies, {}, None, None, None, False, None, None, None)
        assert flag is False

    def test_movie_match_by_name_year(self):
        matcher = SubscribeMatcher()
        media = self._make_media(title="Test", year="2024")
        rss_movies = {"1": {"name": "Test", "year": "2024", "fuzzy_match": False}}
        filter_engine = MagicMock()
        filter_engine.check_torrent_filter.return_value = (True, 1, "ok")
        matcher._filter = filter_engine
        flag, msgs, info = matcher.match(media, rss_movies, {}, None, None, None, False, None, None, None)
        assert flag is True

    def test_movie_fuzzy_match(self):
        matcher = SubscribeMatcher()
        media = self._make_media(title="Test Movie", year="2024")
        rss_movies = {"1": {"name": "Test", "year": "2024", "fuzzy_match": True}}
        filter_engine = MagicMock()
        filter_engine.check_torrent_filter.return_value = (True, 1, "ok")
        matcher._filter = filter_engine
        flag, msgs, info = matcher.match(media, rss_movies, {}, None, None, None, False, None, None, None)
        assert flag is True

    def test_movie_site_filter_excludes(self):
        matcher = SubscribeMatcher()
        media = self._make_media(site="site2")
        rss_movies = {"1": {"name": "Test", "rss_sites": ["site1"], "fuzzy_match": False}}
        flag, msgs, info = matcher.match(media, rss_movies, {}, None, None, None, False, None, None, None)
        assert flag is False

    def test_tv_match_by_season(self):
        matcher = SubscribeMatcher()
        media = self._make_media(mtype=MediaType.TV, tmdb_id="123", title="Test TV")
        rss_tvs = {"1": {"name": "Test TV", "year": "2024", "season": "S01", "tmdbid": "123", "fuzzy_match": False}}
        filter_engine = MagicMock()
        filter_engine.check_torrent_filter.return_value = (True, 1, "ok")
        matcher._filter = filter_engine
        flag, msgs, info = matcher.match(media, {}, rss_tvs, None, None, None, False, None, None, None)
        assert flag is True

    def test_tv_no_match_wrong_season(self):
        matcher = SubscribeMatcher()
        media = self._make_media(mtype=MediaType.TV, tmdb_id="123", title="Test TV")
        media.get_season_string.return_value = "S02"
        rss_tvs = {"1": {"name": "Test TV", "year": "2024", "season": "S01", "tmdbid": "123", "fuzzy_match": False}}
        flag, msgs, info = matcher.match(media, {}, rss_tvs, None, None, None, False, None, None, None)
        assert flag is False

    def test_match_filter_rejected(self):
        matcher = SubscribeMatcher()
        media = self._make_media()
        rss_movies = {"1": {"name": "Test", "year": "2024", "fuzzy_match": False}}
        filter_engine = MagicMock()
        filter_engine.check_torrent_filter.return_value = (False, 0, "filtered out")
        matcher._filter = filter_engine
        flag, msgs, info = matcher.match(media, rss_movies, {}, None, None, None, False, None, None, None)
        assert flag is False
        assert "filtered out" in msgs[0]

    def test_match_with_site_parse_rate_limit(self):
        matcher = SubscribeMatcher()
        media = self._make_media()
        rss_movies = {"1": {"name": "Test", "year": "2024", "fuzzy_match": False}}
        filter_engine = MagicMock()
        filter_engine.check_torrent_filter.return_value = (True, 1, "ok")
        matcher._filter = filter_engine
        with patch("app.services.subscribe.matcher.container.site_cache") as mock_sites:
            mock_sites.return_value.check_ratelimit.return_value = True
            flag, msgs, info = matcher.match(media, rss_movies, {}, 1, None, None, True, None, None, None)
            assert flag is False
            assert "触发站点流控" in msgs[0]

    def test_match_with_site_parse_free(self):
        matcher = SubscribeMatcher()
        media = self._make_media()
        rss_movies = {"1": {"name": "Test", "year": "2024", "fuzzy_match": False, "filter_rule": None}}
        filter_engine = MagicMock()
        filter_engine.check_torrent_filter.return_value = (True, 1, "ok")
        matcher._filter = filter_engine
        with (
            patch("app.services.subscribe.matcher.container.site_cache") as mock_sites,
            patch("app.services.subscribe.matcher.container.site_conf") as mock_siteconf,
        ):
            mock_sites.return_value.check_ratelimit.return_value = False
            mock_siteconf.return_value.check_torrent_attr.return_value = {"free": True}
            media.set_torrent_info = MagicMock()
            flag, msgs, info = matcher.match(media, rss_movies, {}, 1, None, None, True, None, None, None)
            assert flag is True
            media.set_torrent_info.assert_called_once()
            call_kwargs = media.set_torrent_info.call_args.kwargs
            assert call_kwargs["upload_volume_factor"] == 1.0
            assert call_kwargs["download_volume_factor"] == 0.0


class TestSubscribeHistoryService:
    """Test suite for SubscribeHistoryService."""

    def test_get_history(self):
        repo = MagicMock()
        repo.get_all.return_value = [MagicMock(to_dict=lambda: {"id": 1})]
        svc = SubscribeHistoryService(history_repo=repo)
        result = svc.get_history("MOV")
        assert result == [{"id": 1}]
        repo.get_all.assert_called_once_with(rtype="MOV")

    def test_delete(self):
        repo = MagicMock()
        svc = SubscribeHistoryService(history_repo=repo)
        svc.delete("1")
        repo.delete.assert_called_once_with("1")

    def test_redo_no_history(self):
        repo = MagicMock()
        repo.get_all.return_value = []
        svc = SubscribeHistoryService(history_repo=repo)
        code, msg = svc.redo("1", "MOV")
        assert code == -1
        assert "不存在" in msg

    def test_redo_success(self):
        repo = MagicMock()
        history = MagicMock()
        history.name = "Test"
        history.year = "2024"
        history.season = None
        history.tmdb_id = "123"
        history.total = 10
        history.start = 1
        repo.get_all.return_value = [history]
        subscribe = MagicMock()
        subscribe.add_rss_subscribe.return_value = (0, "ok", None)
        svc = SubscribeHistoryService(history_repo=repo, subscribe=subscribe)
        code, msg = svc.redo("1", "MOV")
        assert code == 0
        subscribe.add_rss_subscribe.assert_called_once()

    def test_truncate(self):
        repo = MagicMock()
        subscribe = MagicMock()
        with patch("app.services.subscribe.management.history_service.container.rss_helper") as mock_helper:
            svc = SubscribeHistoryService(history_repo=repo, subscribe=subscribe)
            svc.truncate()
            mock_helper.return_value.truncate_rss_history.assert_called_once()
            subscribe.truncate_rss_episodes.assert_called_once()


class TestSubscribeCalendarService:
    """Test suite for SubscribeCalendarService."""

    def test_get_movie_items(self):
        subscribe = MagicMock()
        subscribe.get_subscribe_movies.return_value = {"1": {"tmdbid": "123", "id": "1"}}
        svc = SubscribeCalendarService(subscribe=subscribe)
        result = svc.get_movie_items()
        assert result == [{"id": "123", "rssid": "1"}]

    def test_get_movie_items_skips_no_tmdbid(self):
        subscribe = MagicMock()
        subscribe.get_subscribe_movies.return_value = {"1": {"tmdbid": None, "id": "1"}}
        svc = SubscribeCalendarService(subscribe=subscribe)
        result = svc.get_movie_items()
        assert result == []

    def test_get_tv_items(self):
        subscribe = MagicMock()
        subscribe.get_subscribe_tvs.return_value = {"1": {"tmdbid": "123", "id": "1", "season": "S01"}}
        rss_task = MagicMock()
        rss_task.get_userrss_mediainfos.return_value = []
        svc = SubscribeCalendarService(subscribe=subscribe, rss_task_service=rss_task)
        result = svc.get_tv_items()
        assert len(result) == 1
        assert result[0]["season"] == 1

    def test_get_tv_items_deduplicates(self):
        subscribe = MagicMock()
        subscribe.get_subscribe_tvs.return_value = {
            "1": {"tmdbid": "123", "id": "1", "season": "S01", "name": "Test"},
            "2": {"tmdbid": "123", "id": "2", "season": "S01", "name": "Test"},
        }
        rss_task = MagicMock()
        rss_task.get_userrss_mediainfos.return_value = []
        svc = SubscribeCalendarService(subscribe=subscribe, rss_task_service=rss_task)
        result = svc.get_tv_items()
        assert len(result) == 1

    def test_get_events(self):
        media_service = MagicMock()
        media_service.get_movie_calendar.return_value = {"id": 1}
        media_service.get_tv_calendar.return_value = [{"id": 2}]
        subscribe = MagicMock()
        subscribe.get_subscribe_movies.return_value = {"1": {"tmdbid": "123", "id": "1"}}
        subscribe.get_subscribe_tvs.return_value = {"1": {"tmdbid": "456", "id": "2", "season": "S01"}}
        rss_task = MagicMock()
        rss_task.get_userrss_mediainfos.return_value = []
        svc = SubscribeCalendarService(media_info_service=media_service, subscribe=subscribe, rss_task_service=rss_task)
        result = svc.get_events()
        assert len(result) == 2
        assert result[0] == {"id": 1}
        assert result[1] == {"id": 2}

    def test_get_events_skips_empty(self):
        media_service = MagicMock()
        media_service.get_movie_calendar.return_value = {}
        media_service.get_tv_calendar.return_value = []
        subscribe = MagicMock()
        subscribe.get_subscribe_movies.return_value = {"1": {"tmdbid": "123", "id": "1"}}
        subscribe.get_subscribe_tvs.return_value = {}
        rss_task = MagicMock()
        rss_task.get_userrss_mediainfos.return_value = []
        svc = SubscribeCalendarService(media_info_service=media_service, subscribe=subscribe, rss_task_service=rss_task)
        result = svc.get_events()
        assert result == []


class TestSubscriptionMonitorTrigger:
    """Test suite for SubscriptionMonitor trigger methods."""

    def test_trigger_calls_run(self):
        monitor = SubscriptionMonitor()
        monitor.run = MagicMock()
        monitor.trigger()
        monitor.run.assert_called_once()

    def test_refresh_subscription_movie(self):
        monitor = SubscriptionMonitor()
        with (
            patch("app.services.subscribe.monitor.SubscribeSearchEngine") as mock_engine,
            patch("app.services.subscribe.monitor.container.thread_executor") as mock_thread,
            patch("app.services.subscribe.monitor.container.subscribe_service"),
        ):
            mock_engine.return_value.subscribe_search_movie = MagicMock()
            monitor.refresh_subscription("MOV", "1")
            mock_thread.return_value.submit.assert_called_once()

    def test_refresh_subscription_tv(self):
        monitor = SubscriptionMonitor()
        with (
            patch("app.services.subscribe.monitor.SubscribeSearchEngine") as mock_engine,
            patch("app.services.subscribe.monitor.container.thread_executor") as mock_thread,
            patch("app.services.subscribe.monitor.container.subscribe_service"),
        ):
            mock_engine.return_value.subscribe_search_tv = MagicMock()
            monitor.refresh_subscription("TV", "1")
            mock_thread.return_value.submit.assert_called_once()

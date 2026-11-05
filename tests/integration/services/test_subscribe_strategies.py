"""Tests for app.services.subscribe coordinator, search engine, and strategies."""

from typing import Any, cast
from unittest.mock import MagicMock, patch

from app.core.settings import settings as app_settings
from app.domain.entities.rss import SubscribeState
from app.domain.mediatypes import MediaType
from app.media.models import MediaInfo
from app.services.subscribe.coordinator import DownloadCoordinator
from app.services.subscribe.search_engine import SubscribeSearchEngine
from app.services.subscribe.strategies.indexer_search import IndexerSearchStrategy
from app.services.subscribe.strategies.queue_search import QueueSearchStrategy
from app.services.subscribe.strategies.rss_feed import RssFeedStrategy


class TestDownloadCoordinator:
    """Test suite for DownloadCoordinator."""

    def _make_media(self, tmdb_id="123", season="S01"):
        media = MagicMock()
        media.tmdb_id = tmdb_id
        media.get_season_string.return_value = season
        return media

    def test_try_acquire_success(self):
        lock_manager = MagicMock()
        lock = MagicMock()
        lock.acquire.return_value = True
        lock_manager.create_lock.return_value = lock
        coord = DownloadCoordinator(lock_manager=lock_manager)
        media = self._make_media()
        assert coord.try_acquire(media) is True
        lock_manager.create_lock.assert_called_once_with("subscribe:download:identity:tmdb:123:S01", ttl_seconds=300)

    def test_try_acquire_already_held(self):
        lock_manager = MagicMock()
        lock = MagicMock()
        lock.acquire.return_value = True
        lock_manager.create_lock.return_value = lock
        coord = DownloadCoordinator(lock_manager=lock_manager)
        media = self._make_media()
        coord.try_acquire(media)
        result = coord.try_acquire(media)
        assert result is True
        assert lock_manager.create_lock.call_count == 2

    def test_try_acquire_failure(self):
        lock_manager = MagicMock()
        lock = MagicMock()
        lock.acquire.return_value = False
        lock_manager.create_lock.return_value = lock
        coord = DownloadCoordinator(lock_manager=lock_manager)
        media = self._make_media()
        assert coord.try_acquire(media) is False

    def test_release(self):
        lock_manager = MagicMock()
        lock = MagicMock()
        lock.acquire.return_value = True
        lock_manager.create_lock.return_value = lock
        coord = DownloadCoordinator(lock_manager=lock_manager)
        media = self._make_media()
        coord.try_acquire(media)
        coord.release(media)
        lock.release.assert_called_once()

    def test_is_locked_local(self):
        lock_manager = MagicMock()
        lock = MagicMock()
        lock.acquire.return_value = True
        lock_manager.create_lock.return_value = lock
        coord = DownloadCoordinator(lock_manager=lock_manager)
        media = self._make_media()
        coord.try_acquire(media)
        assert coord.is_locked(media) is True

    def test_is_locked_not_held(self):
        lock_manager = MagicMock()
        lock = MagicMock()
        lock.acquire.return_value = True
        lock_manager.create_lock.return_value = lock
        coord = DownloadCoordinator(lock_manager=lock_manager)
        media = self._make_media()
        assert coord.is_locked(media) is False

    def test_is_locked_remote_held(self):
        lock_manager = MagicMock()
        local_lock = MagicMock()
        local_lock.acquire.return_value = False
        lock_manager.create_lock.return_value = local_lock
        coord = DownloadCoordinator(lock_manager=lock_manager)
        media = self._make_media()
        assert coord.is_locked(media) is True


class TestSubscribeSearchEngine:
    """Test suite for SubscribeSearchEngine facade."""

    def test_subscribe_search_all(self):
        indexer = MagicMock()
        queue = MagicMock()
        engine = SubscribeSearchEngine(indexer_strategy=indexer, queue_strategy=queue)
        engine.subscribe_search_all()
        indexer.run.assert_called_once()
        queue.run.assert_not_called()

    def test_subscribe_search_state_r(self):
        indexer = MagicMock()
        queue = MagicMock()
        engine = SubscribeSearchEngine(indexer_strategy=indexer, queue_strategy=queue)
        engine.subscribe_search(state="R")
        indexer.run.assert_called_once()
        queue.run.assert_not_called()

    def test_subscribe_search_state_d(self):
        indexer = MagicMock()
        queue = MagicMock()
        engine = SubscribeSearchEngine(indexer_strategy=indexer, queue_strategy=queue)
        engine.subscribe_search(state="D")
        queue.run.assert_called_once()
        indexer.run.assert_not_called()

    def test_subscribe_search_movie_state_r(self):
        indexer = MagicMock()
        queue = MagicMock()
        engine = SubscribeSearchEngine(indexer_strategy=indexer, queue_strategy=queue)
        engine.subscribe_search_movie(rssid=1, state="R")
        indexer._search_movies.assert_called_once_with(state="R", rssid=1, force=False)

    def test_subscribe_search_movie_state_d(self):
        indexer = MagicMock()
        queue = MagicMock()
        engine = SubscribeSearchEngine(indexer_strategy=indexer, queue_strategy=queue)
        engine.subscribe_search_movie(rssid=1, state="D")
        queue._search_movies.assert_called_once_with(state="D", rssid=1, force=False)

    def test_subscribe_search_tv_state_r(self):
        indexer = MagicMock()
        queue = MagicMock()
        engine = SubscribeSearchEngine(indexer_strategy=indexer, queue_strategy=queue)
        engine.subscribe_search_tv(rssid=1, state="R")
        indexer._search_tvs.assert_called_once_with(state="R", rssid=1)

    def test_subscribe_search_tv_state_d(self):
        indexer = MagicMock()
        queue = MagicMock()
        engine = SubscribeSearchEngine(indexer_strategy=indexer, queue_strategy=queue)
        engine.subscribe_search_tv(rssid=1, state="D")
        queue._search_tvs.assert_called_once_with(state="D", rssid=1)


class TestIndexerSearchStrategy:
    """Test suite for IndexerSearchStrategy."""

    def test_run_acquires_lock(self):
        with patch("app.services.subscribe.strategy_lock.get_lock_manager") as mock_lm:
            lock = MagicMock()
            lock.acquire.return_value = True
            mock_lm.return_value.create_lock.return_value = lock
            svc = MagicMock()
            strategy = IndexerSearchStrategy(
                service=svc,
                searcher=MagicMock(),
                media_service=MagicMock(),
                media_cache=MagicMock(),
                downloader=MagicMock(),
                filter_service=MagicMock(),
                message=MagicMock(),
                movie_repo=MagicMock(),
                tv_repo=MagicMock(),
            )
            strategy._search_movies = MagicMock()
            strategy._search_tvs = MagicMock()
            strategy.run()
            lock.acquire.assert_called_once()
            lock.release.assert_called_once()

    def test_run_skips_when_locked(self):
        with patch("app.services.subscribe.strategy_lock.get_lock_manager") as mock_lm:
            lock = MagicMock()
            lock.acquire.return_value = False
            mock_lm.return_value.create_lock.return_value = lock
            strategy = IndexerSearchStrategy(
                service=MagicMock(),
                searcher=MagicMock(),
                media_service=MagicMock(),
                media_cache=MagicMock(),
                downloader=MagicMock(),
                filter_service=MagicMock(),
                message=MagicMock(),
                movie_repo=MagicMock(),
                tv_repo=MagicMock(),
            )
            strategy._search_movies = MagicMock()
            strategy.run()
            strategy._search_movies.assert_not_called()


class TestQueueSearchStrategy:
    """Test suite for QueueSearchStrategy."""

    def test_run_acquires_lock(self):
        with patch("app.services.subscribe.strategy_lock.get_lock_manager") as mock_lm:
            lock = MagicMock()
            lock.acquire.return_value = True
            mock_lm.return_value.create_lock.return_value = lock
            strategy = QueueSearchStrategy(
                service=MagicMock(),
                searcher=MagicMock(),
                media_service=MagicMock(),
                media_cache=MagicMock(),
                downloader=MagicMock(),
                filter_service=MagicMock(),
                message=MagicMock(),
                movie_repo=MagicMock(),
                tv_repo=MagicMock(),
            )
            strategy._search_movies = MagicMock()
            strategy._search_tvs = MagicMock()
            strategy.run()
            lock.acquire.assert_called_once()
            lock.release.assert_called_once()

    def test_run_skips_when_locked(self):
        with patch("app.services.subscribe.strategy_lock.get_lock_manager") as mock_lm:
            lock = MagicMock()
            lock.acquire.return_value = False
            mock_lm.return_value.create_lock.return_value = lock
            strategy = QueueSearchStrategy(
                service=MagicMock(),
                searcher=MagicMock(),
                media_service=MagicMock(),
                media_cache=MagicMock(),
                downloader=MagicMock(),
                filter_service=MagicMock(),
                message=MagicMock(),
                movie_repo=MagicMock(),
                tv_repo=MagicMock(),
            )
            strategy._search_movies = MagicMock()
            strategy.run()
            strategy._search_movies.assert_not_called()


class TestRssFeedStrategy:
    """Test suite for RssFeedStrategy."""

    def _make_strategy(self):
        return RssFeedStrategy(
            media=MagicMock(),
            downloader=MagicMock(),
            sites=MagicMock(),
            siteconf=MagicMock(),
            download_repo=MagicMock(),
            rss_repo=MagicMock(),
            rsshelper=MagicMock(),
            subscribe=MagicMock(),
            matcher=MagicMock(),
            message=MagicMock(),
            coordinator=None,
        )

    def test_run_lock_not_acquired(self):
        strategy = self._make_strategy()
        with patch("app.services.subscribe.strategy_lock.get_lock_manager") as mock_lm:
            lock = MagicMock()
            lock.acquire.return_value = False
            mock_lm.return_value.create_lock.return_value = lock
            strategy.run()
            lock.acquire.assert_called_once()

    def test_do_rss_poll_no_rss_sites(self):
        strategy = self._make_strategy()
        strategy.sites.get_sites.return_value = []  # type: ignore[union-attr]
        strategy.run = lambda: strategy._do_rss_poll()  # type: ignore[method-assign]
        strategy._do_rss_poll()

    def test_do_rss_poll_no_subscriptions(self):
        strategy = self._make_strategy()
        strategy.sites.get_sites.return_value = [{"name": "site1", "rssurl": "http://rss"}]  # type: ignore[union-attr]
        strategy.subscribe.get_subscribe_movies.return_value = {}  # type: ignore[union-attr]
        strategy.subscribe.get_subscribe_tvs.return_value = {}  # type: ignore[union-attr]
        strategy.run = lambda: strategy._do_rss_poll()  # type: ignore[method-assign]
        strategy._do_rss_poll()

    def test_download_matched_torrents_empty(self):
        strategy = self._make_strategy()
        strategy._download_matched_torrents([], {})
        strategy.downloader.batch_download.assert_not_called()  # type: ignore[union-attr]

    def test_download_matched_torrents_no_subscribe(self):
        strategy = self._make_strategy()
        strategy.subscribe = None
        media = MagicMock()
        strategy._download_matched_torrents([media], {})

    def test_download_matched_torrents_with_coordinator(self):
        strategy = self._make_strategy()
        coord = MagicMock()
        coord.try_acquire.return_value = True
        strategy._coordinator = coord
        media = MagicMock()
        media.type = MagicMock()
        media.type.value = "movie"
        media.total_episodes = 0
        media.begin_season = None
        media.begin_episode = None
        media.get_episode_list.return_value = []
        media.res_order = 1
        media.site_order = 1
        media.seeders = 1
        strategy.downloader.batch_download.return_value = ([], [])  # type: ignore[union-attr]
        strategy._download_matched_torrents([media], {})
        coord.try_acquire.assert_called_once()

    def test_rss_download_marks_pending_transfer_not_finish(self):
        """下载覆盖完成后登记“待转移”（COMPLETED），不在此删除订阅、不写历史。"""
        strategy = self._make_strategy()
        media = MagicMock()
        media.type = MediaType.TV
        media.begin_episode = None
        media.enclosure = "http://site/a.torrent"
        media.page_url = "http://site/page"
        media.rssid = 5
        media.over_edition = False
        media.tmdb_id = 1
        media.begin_season = 1
        media.total_episodes = 12
        media.get_episode_list.return_value = list(range(1, 13))
        media.res_order = 1
        media.site_order = 1
        media.seeders = 1
        downloader = cast(Any, strategy.downloader)
        downloader.get_torrent_episodes.return_value = (list(range(1, 13)), "/tmp/a.torrent")
        downloader.batch_download.return_value = ([media], {})

        strategy._download_matched_torrents([media], {1: None})

        subscribe = cast(Any, strategy.subscribe)
        subscribe.finish_rss_subscribe.assert_not_called()
        subscribe.update_rss_state.assert_called_once_with(MediaType.TV, 5, SubscribeState.COMPLETED.value)

    def test_rss_tv_full_coverage_clears_lack_before_completed(self):
        """整季覆盖后清空缺集，避免状态回退时旧缺集触发重复下载."""
        strategy = self._make_strategy()
        media = MediaInfo(title="Demo", type=MediaType.TV)
        media.tmdb_id = "335790"
        media.begin_season = 1
        media.begin_episode = 1
        media.end_episode = 2
        media.total_episodes = 2
        media.rssid = 7
        media.over_edition = False
        media.enclosure = ""
        media.user_id = 1
        cast(Any, strategy.downloader).batch_download.return_value = ([media], {})

        strategy._download_matched_torrents([media], {})

        subscribe = cast(Any, strategy.subscribe)
        subscribe.clear_subscribe_tv_lack.assert_called_once_with(7, media)
        subscribe.update_rss_state.assert_called_once_with(MediaType.TV, 7, SubscribeState.COMPLETED.value)

    def test_rss_movie_marks_pending_transfer(self):
        """电影下载成功登记“待转移”（COMPLETED），由转移落盘确认后定稿。"""
        strategy = self._make_strategy()
        media = MagicMock()
        media.type = MediaType.MOVIE
        media.rssid = 7
        media.over_edition = False
        media.tmdb_id = 9
        media.total_episodes = 0
        media.begin_episode = None
        media.get_episode_list.return_value = []
        media.res_order = 1
        media.site_order = 1
        media.seeders = 1
        downloader = cast(Any, strategy.downloader)
        downloader.batch_download.return_value = ([media], {})

        strategy._download_matched_torrents([media], {})

        subscribe = cast(Any, strategy.subscribe)
        subscribe.finish_rss_subscribe.assert_not_called()
        subscribe.update_rss_state.assert_called_once_with(MediaType.MOVIE, 7, SubscribeState.COMPLETED.value)

    def _movie(self, *, title: str, site_order: int, seeders: int, res_order: int) -> MagicMock:
        media = MagicMock()
        media.type = MediaType.MOVIE
        media.rssid = 7
        media.title = title
        media.site_order = site_order
        media.seeders = seeders
        media.res_order = res_order
        media.over_edition = False
        media.tmdb_id = 9
        media.total_episodes = 0
        media.begin_episode = None
        media.get_episode_list.return_value = []
        return media

    def _selected_movies(self, strategy, medias: list, order: str = "site") -> list:
        cast(Any, strategy.downloader).batch_download.return_value = ([], {})
        with patch.object(
            type(app_settings),
            "get",
            side_effect=lambda key, default=None: {"pt": {"download_order": order}}.get(key, default),
        ):
            strategy._download_matched_torrents(medias, {})
        return cast(Any, strategy.downloader).batch_download.call_args[0][1]

    def test_rss_site_mode_same_site_picks_more_seeders(self):
        """站点优先：同站点内应选做种数最高的，不受 res_order 干扰."""
        strategy = self._make_strategy()
        low_seed = self._movie(title="LowSeed", site_order=9999, seeders=5, res_order=99)
        high_seed = self._movie(title="HighSeed", site_order=9999, seeders=500, res_order=1)

        selected = self._selected_movies(strategy, [low_seed, high_seed])

        assert [item.title for item in selected] == ["HighSeed", "LowSeed"]

    def test_rss_seeder_mode_prefers_more_seeders_over_site(self):
        """做种数优先：低优先级站点做种更多时应胜出."""
        preferred_site = self._movie(title="PreferredSite", site_order=9999, seeders=5, res_order=1)
        other_site = self._movie(title="OtherSite", site_order=0, seeders=500, res_order=99)

        strategy = self._make_strategy()
        selected = self._selected_movies(strategy, [preferred_site, other_site], order="seeder")

        assert [item.title for item in selected] == ["OtherSite", "PreferredSite"]

    def test_rss_movie_keeps_at_most_three_fallback_candidates(self):
        strategy = self._make_strategy()
        medias = [self._movie(title=f"C{i}", site_order=9999, seeders=10 - i, res_order=1) for i in range(5)]

        selected = self._selected_movies(strategy, medias)

        assert [item.title for item in selected] == ["C0", "C1", "C2"]

    def test_rss_site_mode_keeps_higher_priority_site(self):
        """站点优先：低优先级站点做种再多也不能越过站点顺序."""
        preferred_site = self._movie(title="PreferredSite", site_order=9999, seeders=5, res_order=1)
        other_site = self._movie(title="OtherSite", site_order=0, seeders=500, res_order=99)

        strategy = self._make_strategy()
        selected = self._selected_movies(strategy, [other_site, preferred_site])

        assert [item.title for item in selected] == ["PreferredSite", "OtherSite"]

    def test_get_default_rss_sites_no_system_config(self):
        strategy = self._make_strategy()
        strategy._system_config = None
        assert strategy._get_default_rss_sites(MediaType.TV) == []

    def test_get_default_rss_sites_tv(self):
        strategy = self._make_strategy()
        sys_config = MagicMock()
        sys_config.get.return_value = {"rss_sites": ["siteA", "siteB"]}
        strategy._system_config = sys_config
        assert strategy._get_default_rss_sites(MediaType.TV) == ["siteA", "siteB"]

    def test_get_default_rss_sites_movie(self):
        strategy = self._make_strategy()
        sys_config = MagicMock()
        sys_config.get.return_value = {"rss_sites": ["siteM"]}
        strategy._system_config = sys_config
        assert strategy._get_default_rss_sites(MediaType.MOVIE) == ["siteM"]

    def test_get_default_rss_sites_invalid_setting(self):
        strategy = self._make_strategy()
        sys_config = MagicMock()
        sys_config.get.return_value = "not_a_dict"
        strategy._system_config = sys_config
        assert strategy._get_default_rss_sites(MediaType.TV) == []

    def test_get_default_rss_sites_exception_returns_empty(self):
        strategy = self._make_strategy()
        sys_config = MagicMock()
        sys_config.get.side_effect = RuntimeError("db error")
        strategy._system_config = sys_config
        assert strategy._get_default_rss_sites(MediaType.TV) == []

    def test_custom_rss_only_allows_owner_subscriptions(self):
        strategy = self._make_strategy()
        subs = {
            1: {"name": "所有者订阅", "user_id": 7},
            2: {"name": "其他用户订阅", "user_id": 8},
            3: {"name": "系统订阅", "user_id": None},
        }
        item = {"custom_rss": True, "owner_user_id": 7, "site_name": "custom_rss:3"}
        assert list(strategy._filter_subscriptions_for_item(subs, item)) == [1]

    def test_selected_custom_rss_is_polled(self):
        strategy = self._make_strategy()
        strategy_any = cast(Any, strategy)
        custom = MagicMock()
        custom.poll_sites.return_value = [
            {
                "id": -3,
                "source_id": 3,
                "name": "custom_rss:3",
                "rssurl": "https://example.com/feed",
                "custom_rss": True,
                "owner_user_id": 7,
            }
        ]
        custom.poll_articles.return_value = [{"title": "Example", "enclosure": "magnet:?xt=abc"}]
        strategy._custom_rss = custom
        strategy_any.sites.get_sites.return_value = []
        strategy_any.subscribe.get_subscribe_movies.return_value = {
            1: {"name": "Example", "rss_sites": ["custom_rss:3"], "user_id": 7}
        }
        strategy_any.subscribe.get_subscribe_tvs.return_value = {}
        strategy_any.media.identify_batch.return_value = [None]

        strategy._do_rss_poll()

        custom.poll_articles.assert_called_once_with(3)

    def test_unselected_custom_rss_is_not_polled(self):
        strategy = self._make_strategy()
        strategy_any = cast(Any, strategy)
        custom = MagicMock()
        custom.poll_sites.return_value = [
            {"name": "custom_rss:3", "rssurl": "https://example.com/feed", "custom_rss": True}
        ]
        strategy._custom_rss = custom
        strategy_any.sites.get_sites.return_value = []
        strategy_any.subscribe.get_subscribe_movies.return_value = {
            1: {"name": "Example", "rss_sites": ["siteA"], "user_id": 7}
        }
        strategy_any.subscribe.get_subscribe_tvs.return_value = {}

        strategy._do_rss_poll()

        custom.poll_articles.assert_not_called()

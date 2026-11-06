"""Tests for app.services.subscribe.management services."""

from unittest.mock import MagicMock, patch

from app.domain.mediatypes import MediaType
from app.events.bus import EventBus
from app.services.subscribe.management.add_service import SubscribeAddService
from app.services.subscribe.management.finish_service import SubscribeFinishService
from app.services.subscribe.management.refresh_service import SubscribeRefreshService
from app.services.subscribe.management.update_service import SubscribeUpdateService


def _make_subscribe_service(**kwargs):
    """Helper to create SubscribeService with all required mocks."""
    defaults = {
        "movie_repo": MagicMock(),
        "tv_repo": MagicMock(),
        "tv_episode_repo": MagicMock(),
        "history_repo": MagicMock(),
        "message": MagicMock(),
        "media_service": MagicMock(),
        "downloader": MagicMock(),
        "sites": MagicMock(),
        "indexer_service": MagicMock(),
        "filter_service": MagicMock(),
        "event_bus": MagicMock(),
        "system_config": MagicMock(),
    }
    defaults.update(kwargs)
    from app.services.subscribe.management.service import SubscribeService as _SubscribeService

    return _SubscribeService(**defaults)


class TestSubscribeFinishService:
    """Test suite for SubscribeFinishService."""

    def test_finish_rss_subscribe_no_rssid(self):
        svc = SubscribeFinishService(MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock())
        result = svc.finish_rss_subscribe(None, MagicMock(), MagicMock())
        assert result is None

    def test_finish_rss_subscribe_no_media(self):
        svc = SubscribeFinishService(MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock())
        result = svc.finish_rss_subscribe(1, None, MagicMock())
        assert result is None

    def test_finish_movie(self):
        movie_repo = MagicMock()
        rss = MagicMock()
        rss.NAME = "Test Movie"
        rss.YEAR = "2024"
        rss.TMDBID = "123"
        movie_repo.get_all.return_value = [rss]
        history_repo = MagicMock()
        event_bus = MagicMock()
        message = MagicMock()
        delete_fn = MagicMock()
        svc = SubscribeFinishService(movie_repo, MagicMock(), history_repo, message, event_bus)
        media = MagicMock()
        media.type = MediaType.MOVIE
        media.get_poster_image.return_value = "poster.jpg"
        media.overview = "overview"
        media.to_dict.return_value = {}
        svc.finish_rss_subscribe(1, media, delete_fn)
        history_repo.upsert.assert_called_once()
        delete_fn.assert_called_once_with(mtype=MediaType.MOVIE, rssid=1)
        event_bus.publish.assert_called_once()
        message.send_rss_finished_message.assert_called_once()

    def test_finish_tv(self):
        tv_repo = MagicMock()
        rss = MagicMock()
        rss.NAME = "Test TV"
        rss.YEAR = "2024"
        rss.TMDBID = "456"
        rss.TOTAL = 12  # 该季总集数（历史展示取此值）
        rss.TOTAL_EP = None  # 用户未填"总集数"
        rss.SEASON = "S01"
        rss.CURRENT_EP = 12  # 完成时已推进到末集
        tv_repo.get_all.return_value = [rss]
        history_repo = MagicMock()
        event_bus = MagicMock()
        message = MagicMock()
        delete_fn = MagicMock()
        svc = SubscribeFinishService(MagicMock(), tv_repo, history_repo, message, event_bus)
        media = MagicMock()
        media.type = MediaType.TV
        media.get_poster_image.return_value = "poster.jpg"
        media.overview = "overview"
        media.to_dict.return_value = {}
        svc.finish_rss_subscribe(1, media, delete_fn)
        history_repo.upsert.assert_called_once()
        upsert_kwargs = history_repo.upsert.call_args.kwargs
        assert upsert_kwargs["total"] == 12  # 回归：此前取 TOTAL_EP(None) → 历史显示"共 0 集"
        assert upsert_kwargs["start"] == 12
        delete_fn.assert_called_once_with(mtype=MediaType.TV, rssid=1)

    def test_finish_tv_legacy_total_ep_fallback(self):
        """TOTAL 为空（历史数据）时回退用 TOTAL_EP"""
        tv_repo = MagicMock()
        rss = MagicMock()
        rss.NAME = "Legacy TV"
        rss.YEAR = "2020"
        rss.TMDBID = "789"
        rss.TOTAL = None
        rss.TOTAL_EP = 10
        rss.SEASON = "S01"
        rss.CURRENT_EP = 3
        tv_repo.get_all.return_value = [rss]
        history_repo = MagicMock()
        svc = SubscribeFinishService(MagicMock(), tv_repo, history_repo, MagicMock(), MagicMock())
        media = MagicMock()
        media.type = MediaType.TV
        media.to_dict.return_value = {}
        svc.finish_rss_subscribe(1, media, MagicMock())
        assert history_repo.upsert.call_args.kwargs["total"] == 10

    def test_finish_movie_wash_cleans_downloads_by_identity(self):
        movie_repo = MagicMock()
        rss = MagicMock()
        rss.NAME = "Custom Movie"
        rss.YEAR = "2024"
        rss.TMDBID = ""
        rss.IDENTITY_ID = "I1"
        rss.ANCHOR_PROVIDER = "content_id"
        rss.ANCHOR_EXTERNAL_ID = "CUSTOM-0001"
        rss.OVER_EDITION = True
        movie_repo.get_all.return_value = [rss]
        download_repo = MagicMock()
        svc = SubscribeFinishService(
            movie_repo, MagicMock(), MagicMock(), MagicMock(), MagicMock(), download_repo=download_repo
        )
        media = MagicMock()
        media.type = MediaType.MOVIE
        media.to_dict.return_value = {}
        svc.finish_rss_subscribe(1, media, MagicMock())

        download_repo.delete_by_identity.assert_called_once_with(
            identity_id="I1",
            anchor_provider="content_id",
            anchor_external_id="CUSTOM-0001",
            season_prefix=None,
        )
        download_repo.delete_by_tmdb.assert_not_called()

    def test_finish_tv_wash_cleans_downloads_by_identity(self):
        tv_repo = MagicMock()
        rss = MagicMock()
        rss.NAME = "Custom TV"
        rss.YEAR = "2024"
        rss.TMDBID = ""
        rss.IDENTITY_ID = "I2"
        rss.ANCHOR_PROVIDER = "content_id"
        rss.ANCHOR_EXTERNAL_ID = "CUSTOM-0002"
        rss.OVER_EDITION = True
        rss.SEASON = "S01"
        rss.CURRENT_EP = 3
        rss.TOTAL = 3
        rss.TOTAL_EP = 3
        tv_repo.get_all.return_value = [rss]
        download_repo = MagicMock()
        svc = SubscribeFinishService(
            MagicMock(), tv_repo, MagicMock(), MagicMock(), MagicMock(), download_repo=download_repo
        )
        media = MagicMock()
        media.type = MediaType.TV
        media.get_season_string.return_value = "S01"
        media.to_dict.return_value = {}
        svc.finish_rss_subscribe(1, media, MagicMock())

        download_repo.delete_by_identity.assert_called_once_with(
            identity_id="I2",
            anchor_provider="content_id",
            anchor_external_id="CUSTOM-0002",
            season_prefix="S01",
        )
        download_repo.delete_by_tmdb.assert_not_called()

    def test_finish_no_rss_found(self):
        movie_repo = MagicMock()
        movie_repo.get_all.return_value = []
        svc = SubscribeFinishService(movie_repo, MagicMock(), MagicMock(), MagicMock(), MagicMock())
        media = MagicMock()
        media.type = MediaType.MOVIE
        result = svc.finish_rss_subscribe(1, media, MagicMock())
        assert result is None


class TestSubscribeUpdateService:
    """Test suite for SubscribeUpdateService."""

    def test_update_no_rssid(self):
        svc = SubscribeUpdateService(
            MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock()
        )
        code, msg, media = svc.update_rss_subscribe(mtype=MediaType.MOVIE, rssid=None)
        assert code == -1
        assert "缺少订阅ID" in msg

    def test_update_movie_success(self):
        movie_repo = MagicMock()
        movie_repo.update.return_value = 0
        movie_repo.get_all.return_value = []
        media_service = MagicMock()
        media_info = MagicMock()
        media_info.provider_data = {"id": 1}
        media_info.type = MediaType.MOVIE
        media_info.title = "Test"
        media_info.year = "2024"
        media_info.tmdb_id = "123"
        media_info.to_dict.return_value = {}
        media_service.get_media_info.return_value = media_info
        event_bus = MagicMock()
        svc = SubscribeUpdateService(
            movie_repo, MagicMock(), media_service, MagicMock(), event_bus, MagicMock(), MagicMock()
        )
        with patch("app.services.subscribe.management.update_service.gen_rss_note", return_value="{}"):
            code, msg, result = svc.update_rss_subscribe(
                mtype=MediaType.MOVIE, rssid=1, name="Test", year="2024", state="D"
            )
        assert code == 0
        assert "成功" in msg
        movie_repo.update.assert_called_once()
        args = movie_repo.update.call_args
        assert args.kwargs["filter_rule"] == 0
        assert args.kwargs["download_setting"] == -1

    def test_update_douban_subscription_resolves_douban_not_tmdb(self):
        """多元数据订阅按自身来源解析：豆瓣订阅编辑不应查询 TMDB."""
        from types import SimpleNamespace

        movie_repo = MagicMock()
        movie_repo.update.return_value = 0
        movie_repo.get_all.return_value = [
            SimpleNamespace(
                NAME="旧标题",
                YEAR="2024",
                IMAGE="",
                TMDBID="",
                ANCHOR_PROVIDER="db",
                ANCHOR_EXTERNAL_ID="123",
                CONTENT_PROFILE="default",
                PROVIDER="db",
                METADATA_REF="db:123",
                KEYWORD="",
                IDENTITY_ID="id-db",
                STATE="R",
            )
        ]
        media_service = MagicMock()
        web_utils = MagicMock()
        resolved = MagicMock()
        resolved.title = "豆瓣新标题"
        resolved.year = "2025"
        resolved.get_poster_image.return_value = "https://example.com/db.jpg"
        web_utils.get_mediainfo_from_id.return_value = resolved
        svc = SubscribeUpdateService(
            movie_repo, MagicMock(), media_service, MagicMock(), MagicMock(), MagicMock(), web_utils
        )

        code, _msg, _result = svc.update_rss_subscribe(mtype=MediaType.MOVIE, rssid=1)

        assert code == 0
        web_utils.get_mediainfo_from_id.assert_called_once_with(mtype=MediaType.MOVIE, mediaid="db:123")
        media_service.get_media_info.assert_not_called()
        args = movie_repo.update.call_args.kwargs
        assert args["name"] == "豆瓣新标题"
        assert args["year"] == "2025"
        assert args["state"] == "R"

    def test_update_existing_movie_falls_back_when_tmdb_lookup_fails(self):
        """编辑已有订阅时 TMDB 查询失败不应导致保存失败，保留原身份更新."""
        from types import SimpleNamespace

        movie_repo = MagicMock()
        movie_repo.update.return_value = 0
        existing = SimpleNamespace(
            NAME="Demo",
            YEAR="2026",
            IMAGE="https://example.com/p.jpg",
            TMDBID="999",
            ANCHOR_PROVIDER="tmdb",
            ANCHOR_EXTERNAL_ID="999",
            CONTENT_PROFILE="default",
            PROVIDER="tmdb",
            METADATA_REF="tmdb:999",
            KEYWORD="",
            IDENTITY_ID="id-999",
            STATE="R",
        )
        movie_repo.get_all.return_value = [existing]
        media_service = MagicMock()
        media_info = MagicMock()
        media_info.provider_data = None
        media_service.get_media_info.return_value = media_info
        svc = SubscribeUpdateService(
            movie_repo, MagicMock(), media_service, MagicMock(), MagicMock(), MagicMock(), MagicMock()
        )

        code, msg, _result = svc.update_rss_subscribe(
            mtype=MediaType.MOVIE, rssid=1, name="Demo", year="2026", state="D"
        )

        assert code == 0
        assert "成功" in msg
        args = movie_repo.update.call_args.kwargs
        assert args["tmdbid"] == "999"
        assert args["identity_id"] == "id-999"
        assert args["anchor_provider"] == "tmdb"

    def test_update_tv_no_total_episode(self):
        from types import SimpleNamespace

        tv_repo = MagicMock()
        tv_repo.get_all.return_value = [
            SimpleNamespace(
                NAME="Test",
                YEAR="2024",
                TMDBID="999",
                ANCHOR_PROVIDER="tmdb",
                ANCHOR_EXTERNAL_ID="999",
                CONTENT_PROFILE="default",
                PROVIDER="tmdb",
                METADATA_REF="tmdb:999",
            )
        ]
        media_service = MagicMock()
        media_info = MagicMock()
        media_info.provider_data = {"id": 1}
        media_info.type = MediaType.TV
        media_info.title = "Test"
        media_info.year = "2024"
        media_info.begin_season = 1
        media_service.get_media_info.return_value = media_info
        media_service.get_tmdb_season_episodes_num.return_value = None
        svc = SubscribeUpdateService(
            MagicMock(), tv_repo, media_service, MagicMock(), MagicMock(), MagicMock(), MagicMock()
        )
        code, msg, result = svc.update_rss_subscribe(
            mtype=MediaType.TV, rssid=1, name="Test", year="2024", season=1, state="D"
        )
        assert code == 3

    def test_update_fuzzy_match_movie(self):
        movie_repo = MagicMock()
        movie_repo.update.return_value = 0
        svc = SubscribeUpdateService(
            movie_repo, MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock()
        )
        code, msg, result = svc.update_rss_subscribe(
            mtype=MediaType.MOVIE, rssid=1, name="Test", fuzzy_match=True, state="D"
        )
        assert code == 0
        movie_repo.update.assert_called_once()


class TestSubscribeAddService:
    """Test suite for SubscribeAddService."""

    def test_add_no_name(self):
        svc = SubscribeAddService(
            MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock()
        )
        code, msg, media = svc.add_rss_subscribe(mtype=MediaType.MOVIE, name=None, year="2024")
        assert code == -1
        assert "标题" in msg

    def test_add_movie_success(self):
        movie_repo = MagicMock()
        movie_repo.insert.return_value = 1
        media_service = MagicMock()
        media_info = MagicMock()
        media_info.provider_data = {"id": 1}
        media_info.type = MediaType.MOVIE
        media_info.title = "Test"
        media_info.year = "2024"
        media_info.tmdb_id = "123"
        media_info.to_dict.return_value = {}
        media_service.get_media_info.return_value = media_info
        event_bus = MagicMock()
        system_config = MagicMock()
        system_config.get.return_value = None
        svc = SubscribeAddService(
            movie_repo, MagicMock(), media_service, MagicMock(), event_bus, system_config, MagicMock()
        )
        with patch("app.services.subscribe.management.add_service.gen_rss_note", return_value="{}"):
            code, msg, result = svc.add_rss_subscribe(mtype=MediaType.MOVIE, name="Test", year="2024")
        assert code == 0
        assert "成功" in msg
        movie_repo.insert.assert_called_once()
        args = movie_repo.insert.call_args
        assert args.kwargs["filter_rule"] == 0
        assert args.kwargs["download_setting"] == -1
        event_payload = event_bus.publish.call_args[0][0].payload
        assert event_payload["rssid"] == 1

    def test_add_tv_success(self):
        tv_repo = MagicMock()
        tv_repo.insert.return_value = 2
        media_service = MagicMock()
        media_info = MagicMock()
        media_info.provider_data = {"id": 1}
        media_info.type = MediaType.TV
        media_info.title = "Test"
        media_info.year = "2024"
        media_info.begin_season = 1
        media_info.tmdb_id = "123"
        media_info.total_episodes = 10
        media_info.to_dict.return_value = {}
        media_service.get_media_info.return_value = media_info
        media_service.get_tmdb_season_episodes_num.return_value = 10
        event_bus = MagicMock()
        svc = SubscribeAddService(MagicMock(), tv_repo, media_service, MagicMock(), event_bus, MagicMock(), MagicMock())
        with patch("app.services.subscribe.management.add_service.gen_rss_note", return_value="{}"):
            code, msg, result = svc.add_rss_subscribe(mtype=MediaType.TV, rssid=1, name="Test", year="2024", season=1)
        assert code == 0
        assert "成功" in msg
        tv_repo.insert.assert_called_once()
        event_payload = event_bus.publish.call_args[0][0].payload
        assert event_payload["rssid"] == 2

    def test_add_fuzzy_match_movie(self):
        movie_repo = MagicMock()
        movie_repo.insert.return_value = 0
        svc = SubscribeAddService(
            movie_repo, MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock()
        )
        code, msg, result = svc.add_rss_subscribe(
            mtype=MediaType.MOVIE, rssid=1, name="Test", year="2024", fuzzy_match=True
        )
        assert code == 0
        movie_repo.insert.assert_called_once()

    def test_add_default_settings(self):
        movie_repo = MagicMock()
        movie_repo.insert.return_value = 0
        media_service = MagicMock()
        media_info = MagicMock()
        media_info.provider_data = {"id": 1}
        media_info.type = MediaType.MOVIE
        media_info.title = "Test"
        media_info.year = "2024"
        media_info.tmdb_id = "123"
        media_info.to_dict.return_value = {}
        media_service.get_media_info.return_value = media_info
        system_config = MagicMock()
        system_config.get.return_value = {
            "restype": "BluRay",
            "pix": "1080p",
            "rss_sites": ["site1"],
        }
        svc = SubscribeAddService(
            movie_repo, MagicMock(), media_service, MagicMock(), MagicMock(), system_config, MagicMock()
        )
        with patch("app.services.subscribe.management.add_service.gen_rss_note", return_value="{}"):
            code, msg, result = svc.add_rss_subscribe(mtype=MediaType.MOVIE, name="Test", year="2024")
        assert code == 0
        movie_repo.insert.assert_called_once()
        assert movie_repo.insert.call_args.kwargs["rss_sites"] == ["site1"]

    def test_add_snapshots_visible_sites_when_no_defaults(self):
        """新增订阅必须把当前可见站点写入数据库，而不是留空依赖运行时兜底."""
        movie_repo = MagicMock()
        movie_repo.insert.return_value = 0
        media_service = MagicMock()
        media_info = MagicMock()
        media_info.provider_data = {"id": 1}
        media_info.type = MediaType.MOVIE
        media_info.title = "Test"
        media_info.year = "2024"
        media_info.tmdb_id = "123"
        media_info.to_dict.return_value = {}
        media_service.get_media_info.return_value = media_info
        system_config = MagicMock()
        system_config.get.return_value = {}
        site_cache = MagicMock()
        site_cache.get_site_names.return_value = ["M-Team"]
        indexer_service = MagicMock()
        indexer_service.get_user_indexer_names.return_value = ["M-Team", "观众"]
        svc = SubscribeAddService(
            movie_repo,
            MagicMock(),
            media_service,
            MagicMock(),
            MagicMock(),
            system_config,
            MagicMock(),
            site_cache=site_cache,
            indexer_service=indexer_service,
        )

        with patch("app.services.subscribe.management.add_service.gen_rss_note", return_value="{}"):
            code, _msg, _result = svc.add_rss_subscribe(mtype=MediaType.MOVIE, name="Test", year="2024")

        assert code == 0
        kwargs = movie_repo.insert.call_args.kwargs
        assert kwargs["rss_sites"] == ["M-Team"]
        assert kwargs["search_sites"] == ["M-Team", "观众"]

    def test_add_movie_exists(self):
        movie_repo = MagicMock()
        movie_repo.insert.return_value = 9
        media_service = MagicMock()
        media_info = MagicMock()
        media_info.provider_data = {"id": 1}
        media_info.type = MediaType.MOVIE
        media_info.to_dict.return_value = {}
        media_service.get_media_info.return_value = media_info
        svc = SubscribeAddService(
            movie_repo, MagicMock(), media_service, MagicMock(), MagicMock(), MagicMock(), MagicMock()
        )
        with patch("app.services.subscribe.management.add_service.gen_rss_note", return_value="{}"):
            code, msg, result = svc.add_rss_subscribe(mtype=MediaType.MOVIE, name="Test", year="2024")
        assert code == 9
        assert "已存在" in msg

    def test_add_fuzzy_match(self):
        movie_repo = MagicMock()
        movie_repo.insert.return_value = 0
        svc = SubscribeAddService(
            movie_repo, MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock()
        )
        code, msg, result = svc.add_rss_subscribe(mtype=MediaType.MOVIE, name="Test", year="2024", fuzzy_match=True)
        assert code == 0
        assert movie_repo.insert.call_args.kwargs["fuzzy_match"] == 1


class TestSubscribeRefreshService:
    """Test suite for SubscribeRefreshService."""

    def test_refresh_no_tmdb_change(self):
        movie_repo = MagicMock()
        tv_repo = MagicMock()
        media_service = MagicMock()
        media_info = MagicMock()
        media_info.tmdb_id = None
        media_service.get_media_info.return_value = media_info
        svc = SubscribeRefreshService(movie_repo, tv_repo, MagicMock(), media_service)
        svc.refresh_rss_metainfo(
            get_subscribe_movies_fn=lambda state="R": {"1": {"id": 1, "name": "Test", "fuzzy_match": False}},
            get_subscribe_tvs_fn=lambda state="R": {},
        )
        movie_repo.update_tmdb.assert_not_called()

    def test_refresh_movie_with_tmdb_change(self):
        movie_repo = MagicMock()
        media_service = MagicMock()
        media_info = MagicMock()
        media_info.tmdb_id = "123"
        media_info.title = "New Title"
        media_info.year = "2024"
        media_info.overview = "desc"
        media_info.get_message_image.return_value = "img.jpg"
        media_service.get_media_info.return_value = media_info
        svc = SubscribeRefreshService(movie_repo, MagicMock(), MagicMock(), media_service)
        with patch("app.services.subscribe.management.refresh_service.gen_rss_note", return_value="{}"):
            svc.refresh_rss_metainfo(
                get_subscribe_movies_fn=lambda state="R": {"1": {"id": 1, "name": "Old", "fuzzy_match": False}},
                get_subscribe_tvs_fn=lambda state="R": {},
            )
        movie_repo.update_tmdb.assert_called_once()

    def test_refresh_skips_fuzzy_match(self):
        movie_repo = MagicMock()
        svc = SubscribeRefreshService(movie_repo, MagicMock(), MagicMock(), MagicMock())
        svc.refresh_rss_metainfo(
            get_subscribe_movies_fn=lambda state="R": {"1": {"id": 1, "name": "Test", "fuzzy_match": True}},
            get_subscribe_tvs_fn=lambda state="R": {},
        )
        movie_repo.update_tmdb.assert_not_called()

    def test_refresh_tv_with_tmdb(self):
        tv_repo = MagicMock()
        media_service = MagicMock()
        media_info = MagicMock()
        media_info.tmdb_id = "456"
        media_info.title = "New TV"
        media_info.year = "2024"
        media_info.overview = "desc"
        media_info.get_message_image.return_value = "img.jpg"
        media_service.get_media_info.return_value = media_info
        media_service.get_tmdb_season_episodes_num.return_value = 12
        svc = SubscribeRefreshService(MagicMock(), tv_repo, MagicMock(), media_service)
        with (
            patch("app.services.subscribe.management.refresh_service.transaction_scope"),
            patch("app.services.subscribe.management.refresh_service.gen_rss_note", return_value="{}"),
        ):
            svc.refresh_rss_metainfo(
                get_subscribe_movies_fn=lambda state="R": {},
                get_subscribe_tvs_fn=lambda state="R": {
                    "1": {"id": 1, "name": "Old TV", "fuzzy_match": False, "season": "S01", "total": 10, "lack": 2}
                },
            )
            tv_repo.update_tmdb.assert_called_once()

    def test_refresh_skips_when_has_tmdbid(self):
        movie_repo = MagicMock()
        svc = SubscribeRefreshService(movie_repo, MagicMock(), MagicMock(), MagicMock())
        svc.refresh_rss_metainfo(
            get_subscribe_movies_fn=lambda state="R": {
                "1": {"id": 1, "name": "Test", "fuzzy_match": False, "tmdbid": "123"}
            },
            get_subscribe_tvs_fn=lambda state="R": {},
        )
        movie_repo.update_tmdb.assert_not_called()


class TestSubscribeService:
    """Test suite for SubscribeService facade."""

    def test_default_settings(self):
        system_config = MagicMock()
        system_config.get.return_value = {"restype": "BluRay"}
        svc = _make_subscribe_service(system_config=system_config)
        assert svc.default_subscribe_setting_tv == {"restype": "BluRay"}
        assert svc.default_subscribe_setting_mov == {"restype": "BluRay"}

    def test_update_rss_state_movie_running(self):
        movie_repo = MagicMock()
        entity = MagicMock()
        movie_repo.get_all.return_value = [entity]
        svc = _make_subscribe_service(movie_repo=movie_repo)
        svc.update_rss_state(MediaType.MOVIE, 1, "R")
        entity.mark_running.assert_called_once()
        movie_repo.update.assert_called_once()

    def test_update_rss_state_movie_completed(self):
        tv_repo = MagicMock()
        entity = MagicMock()
        tv_repo.get_all.return_value = [entity]
        svc = _make_subscribe_service(tv_repo=tv_repo)
        svc.update_rss_state(MediaType.TV, 1, "C")
        entity.mark_completed.assert_called_once()

    def test_update_rss_state_no_entity(self):
        movie_repo = MagicMock()
        movie_repo.get_all.return_value = []
        svc = _make_subscribe_service(movie_repo=movie_repo)
        result = svc.update_rss_state(MediaType.MOVIE, 1, "R")
        assert result is None

    def test_update_subscribe_over_edition_finish(self):
        movie_repo = MagicMock()
        filter_service = MagicMock()
        filter_service.get_rule_first_order.return_value = 5
        media = MagicMock()
        media.res_order = 10
        media.filter_rule = "1"
        svc = _make_subscribe_service(movie_repo=movie_repo, filter_service=filter_service)
        with (
            patch.object(svc, "finish_rss_subscribe") as mock_finish,
            patch.object(svc, "update_rss_state") as mock_update,
        ):
            result = svc.update_subscribe_over_edition(MediaType.MOVIE, 1, media)
            assert result is True
            mock_finish.assert_not_called()
            mock_update.assert_called_once_with(rtype=MediaType.MOVIE, rssid=1, state="C")

    def test_update_subscribe_over_edition_tv_still_finishes(self):
        tv_repo = MagicMock()
        filter_service = MagicMock()
        filter_service.get_rule_first_order.return_value = 5
        media = MagicMock()
        media.res_order = 10
        media.filter_rule = "1"
        svc = _make_subscribe_service(tv_repo=tv_repo, filter_service=filter_service)
        with patch.object(svc, "finish_rss_subscribe") as mock_finish:
            result = svc.update_subscribe_over_edition(MediaType.TV, 1, media)
            assert result is True
            mock_finish.assert_called_once()

    def test_update_subscribe_over_edition_continue(self):
        movie_repo = MagicMock()
        filter_service = MagicMock()
        filter_service.get_rule_first_order.return_value = 10
        media = MagicMock()
        media.res_order = 5
        media.filter_rule = "1"
        svc = _make_subscribe_service(movie_repo=movie_repo, filter_service=filter_service)
        with patch.object(svc, "update_rss_state") as mock_update:
            result = svc.update_subscribe_over_edition(MediaType.MOVIE, 1, media)
            assert result is False
            mock_update.assert_called_once()

    def test_check_subscribe_over_edition_no_pre(self):
        movie_repo = MagicMock()
        movie_repo.get_filter_order.return_value = None
        svc = _make_subscribe_service(movie_repo=movie_repo)
        assert svc.check_subscribe_over_edition(MediaType.MOVIE, 1, 5) is True

    def test_check_subscribe_over_edition_higher(self):
        movie_repo = MagicMock()
        movie_repo.get_filter_order.return_value = 5
        svc = _make_subscribe_service(movie_repo=movie_repo)
        assert svc.check_subscribe_over_edition(MediaType.MOVIE, 1, 10) is True

    def test_check_subscribe_over_edition_lower(self):
        movie_repo = MagicMock()
        movie_repo.get_filter_order.return_value = 10
        svc = _make_subscribe_service(movie_repo=movie_repo)
        assert svc.check_subscribe_over_edition(MediaType.MOVIE, 1, 5) is False

    def test_update_subscribe_tv_lack(self):
        tv_repo = MagicMock()
        media_info = MagicMock()
        media_info.get_season_seq.return_value = "1"
        media_info.get_title_string.return_value = "Test"
        media_info.get_season_string.return_value = "S01"
        svc = _make_subscribe_service(tv_repo=tv_repo)
        svc.update_subscribe_tv_lack(1, media_info, [{"season": 1, "episodes": [1, 2]}])
        tv_repo.update_state.assert_called_once()
        tv_repo.update_lack.assert_called_once()

    def test_update_subscribe_tv_lack_no_seasoninfo(self):
        tv_repo = MagicMock()
        media_info = MagicMock()
        svc = _make_subscribe_service(tv_repo=tv_repo)
        svc.update_subscribe_tv_lack(1, media_info, None)
        tv_repo.update_lack.assert_not_called()

    def test_truncate_rss_episodes(self):
        tv_episode_repo = MagicMock()
        svc = _make_subscribe_service(tv_episode_repo=tv_episode_repo)
        svc.truncate_rss_episodes()
        tv_episode_repo.delete_all.assert_called_once()

    def test_event_handler_registration(self):
        """测试 @on_event 装饰器是否正确注册到 EventBus."""
        from app.events.bridge import PluginBridge
        from app.events.registry import EventHandlerRegistry

        registry = EventHandlerRegistry()
        bus = EventBus(registry=registry, bridge=PluginBridge(hook_system=MagicMock()))
        # 手动注册一个测试 handler，验证机制正常
        bus.subscribe("test.event", lambda e: None)
        assert len(registry.get_handlers("test.event")) == 1

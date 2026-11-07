"""Subscription API Router 单元测试."""

from unittest.mock import ANY, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import (
    get_app_context,
    get_current_user,
    get_subscribe_calendar_service,
    get_subscribe_history_service,
    get_subscribe_service,
    get_subscription_monitor,
    get_system_config_service,
)
from api.routers import subscription as subscription_router
from app.domain.media_types import ProviderMediaType
from app.schemas.auth import UserContext


class _MockMediaInfo:
    tmdb_id = 123


@pytest.fixture
def mock_subscribe_service():
    svc = MagicMock()
    svc.add_rss_subscribe.return_value = (0, "ok", _MockMediaInfo())
    svc.update_rss_subscribe.return_value = (0, "ok", _MockMediaInfo())
    svc.get_subscribe_id.return_value = 42
    svc.cancel_subscribe.return_value = None
    svc.get_subscribe_movies.return_value = {"1": {"title": "Movie"}}
    svc.get_subscribe_tvs.return_value = {"1": {"title": "TV"}}
    svc.default_subscribe_setting_tv = {"restype": "1080p"}
    svc.default_subscribe_setting_mov = {"restype": "4k"}
    return svc


@pytest.fixture
def mock_history_service():
    svc = MagicMock()
    svc.delete.return_value = None
    svc.redo.return_value = (0, "ok")
    svc.get_history.return_value = []
    svc.truncate.return_value = None
    return svc


@pytest.fixture
def mock_calendar_service():
    svc = MagicMock()
    svc.get_events.return_value = []
    svc.get_movie_items.return_value = []
    svc.get_tv_items.return_value = []
    return svc


@pytest.fixture
def mock_monitor():
    return MagicMock()


@pytest.fixture
def mock_system_config():
    cfg = MagicMock()
    cfg.set.return_value = None

    def _get(key):
        name = str(getattr(key, "value", key))
        if name.startswith("DefaultSubscribeSettingTV"):
            return {"restype": "1080p"}
        if name.startswith("DefaultSubscribeSettingMovie"):
            return {"restype": "4k"}
        return {}

    cfg.get.side_effect = _get
    return cfg


@pytest.fixture
def client(
    mock_subscribe_service,
    mock_history_service,
    mock_calendar_service,
    mock_monitor,
    mock_system_config,
):
    app = FastAPI()
    app.include_router(subscription_router.router, prefix="/api/v1/subscription")
    admin_ctx = UserContext(
        user_id=1,
        username="admin",
        level=0,
        permissions=["subscription:view", "subscription:manage"],
    )
    app.dependency_overrides[get_current_user] = lambda: admin_ctx
    mock_app_context = MagicMock()
    mock_app_context.site_grant_service = None
    app.dependency_overrides[get_app_context] = lambda: mock_app_context
    app.dependency_overrides[get_subscribe_service] = lambda: mock_subscribe_service
    app.dependency_overrides[get_subscribe_history_service] = lambda: mock_history_service
    app.dependency_overrides[get_subscribe_calendar_service] = lambda: mock_calendar_service
    app.dependency_overrides[get_subscription_monitor] = lambda: mock_monitor
    app.dependency_overrides[get_system_config_service] = lambda: mock_system_config
    with TestClient(app) as c:
        yield c


class TestSubscriptionRouter:
    def test_add_rss_media(self, client, mock_subscribe_service):
        resp = client.post("/api/v1/subscription/add", json={"name": "Test", "type": "movie"})
        assert resp.status_code == 200
        assert resp.json()["data"]["rssid"] == 42
        mock_subscribe_service.add_rss_subscribe.assert_called_once()

    def test_add_rss_media_season_list(self, client, mock_subscribe_service):
        resp = client.post("/api/v1/subscription/add", json={"name": "Test", "type": "tv", "season": "S01"})
        assert resp.status_code == 200
        mock_subscribe_service.add_rss_subscribe.assert_called_once()

    def test_add_rss_media_forwards_start_episode(self, client, mock_subscribe_service):
        """新增订阅需把开始集数/总集数传给服务层（此前漏传 → 从第 1 集开始下载）"""
        resp = client.post(
            "/api/v1/subscription/add",
            json={"name": "Test", "type": "tv", "season": "1", "total_ep": 12, "current_ep": 5},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        kwargs = mock_subscribe_service.add_rss_subscribe.call_args.kwargs
        assert kwargs["total_ep"] == 12
        assert kwargs["current_ep"] == 5

    def test_update_rss_media_forwards_start_episode(self, client, mock_subscribe_service):
        resp = client.post(
            "/api/v1/subscription/update",
            json={"rssid": "1", "name": "Test", "type": "tv", "season": "1", "total_ep": 12, "current_ep": 5},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        kwargs = mock_subscribe_service.update_rss_subscribe.call_args.kwargs
        assert kwargs["total_ep"] == 12
        assert kwargs["current_ep"] == 5

    def test_update_rss_media_missing_id(self, client):
        resp = client.post("/api/v1/subscription/update", json={"name": "Test"})
        assert resp.status_code == 200
        assert resp.json()["code"] != 0

    def test_update_rss_media(self, client, mock_subscribe_service):
        resp = client.post("/api/v1/subscription/update", json={"rssid": "1", "name": "Test", "type": "movie"})
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        assert resp.json()["data"]["rssid"] == 1
        mock_subscribe_service.update_rss_subscribe.assert_called_once()

    def test_save_default_setting_anime_writes_tv_key(self, client, mock_system_config):
        """动漫保存默认设置应落到电视剧键（否则被静默丢弃，AI 新增订阅拿不到默认设置）"""
        resp = client.post(
            "/api/v1/subscription/default_setting/save",
            json={"mtype": "anime", "restype": "1080p"},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        mock_system_config.set.assert_called_once()
        assert mock_system_config.set.call_args.kwargs["key"] == "DefaultSubscribeSettingTV::u1"

    def test_delete_rss_history(self, client, mock_history_service):
        resp = client.post("/api/v1/subscription/history/delete", json={"rssid": "1"})
        assert resp.status_code == 200
        mock_history_service.delete.assert_called_once_with(rssid=1, user=ANY)

    def test_re_rss_history(self, client, mock_history_service):
        resp = client.post("/api/v1/subscription/history/redo", json={"rssid": "1", "type": "movie"})
        assert resp.status_code == 200
        mock_history_service.redo.assert_called_once()

    def test_refresh_rss(self, client, mock_monitor):
        resp = client.post("/api/v1/subscription/refresh", json={"type": "movie", "rssid": "1"})
        assert resp.status_code == 200
        mock_monitor.refresh_subscription.assert_called_once_with(mtype="movie", rssid=1)

    def test_remove_rss_media_movie(self, client, mock_subscribe_service):
        resp = client.post(
            "/api/v1/subscription/remove",
            json={"name": "Movie", "type": "movie", "rssid": "1", "tmdbid": "123"},
        )
        assert resp.status_code == 200
        mock_subscribe_service.cancel_subscribe.assert_called_once()

    def test_remove_rss_media_tv(self, client, mock_subscribe_service):
        resp = client.post(
            "/api/v1/subscription/remove",
            json={"name": "TV", "type": "tv", "season": "S01", "rssid": "1"},
        )
        assert resp.status_code == 200
        args = mock_subscribe_service.cancel_subscribe.call_args
        assert args.kwargs["mtype"].value == "tv"

    def test_remove_rss_media_rssid_only(self, client, mock_subscribe_service):
        resp = client.post("/api/v1/subscription/remove", json={"rssid": "1"})
        assert resp.status_code == 200
        assert mock_subscribe_service.cancel_subscribe.call_count == 2
        mtypes = {c.kwargs["mtype"] for c in mock_subscribe_service.cancel_subscribe.call_args_list}
        assert ProviderMediaType.MOVIE in mtypes
        assert ProviderMediaType.SERIES in mtypes

    def test_rss_detail_movie(self, client, mock_subscribe_service):
        resp = client.post("/api/v1/subscription/detail", json={"rssid": "1", "rsstype": "movie"})
        assert resp.status_code == 200
        assert resp.json()["data"]["type"] == "movie"

    def test_rss_detail_tv(self, client, mock_subscribe_service):
        resp = client.post("/api/v1/subscription/detail", json={"rssid": "1", "rsstype": "tv"})
        assert resp.status_code == 200
        assert resp.json()["data"]["type"] == "tv"

    def test_get_default_rss_setting_tv(self, client, mock_subscribe_service):
        resp = client.post("/api/v1/subscription/default_setting", json={"mtype": "tv"})
        assert resp.status_code == 200
        assert resp.json()["data"]["restype"] == "1080p"

    def test_get_default_rss_setting_mov(self, client, mock_subscribe_service):
        resp = client.post("/api/v1/subscription/default_setting", json={"mtype": "movie"})
        assert resp.status_code == 200
        assert resp.json()["data"]["restype"] == "4k"

    def test_get_default_rss_setting_empty(self, client, mock_system_config):
        mock_system_config.get.side_effect = None
        mock_system_config.get.return_value = None
        resp = client.post("/api/v1/subscription/default_setting", json={"mtype": "tv"})
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        assert resp.json()["data"] == {}

    def test_save_default_rss_setting(self, client, mock_system_config):
        resp = client.post(
            "/api/v1/subscription/default_setting/save",
            json={"mtype": "tv", "over_edition": "1", "restype": "1080p"},
        )
        assert resp.status_code == 200
        mock_system_config.set.assert_called_once()

    def test_get_ical_events(self, client, mock_calendar_service):
        resp = client.post("/api/v1/subscription/calendar/ical", json={})
        assert resp.status_code == 200
        mock_calendar_service.get_events.assert_called_once()

    def test_get_movie_rss_items(self, client, mock_calendar_service):
        resp = client.post("/api/v1/subscription/movie/items", json={})
        assert resp.status_code == 200
        mock_calendar_service.get_movie_items.assert_called_once()

    def test_get_movie_rss_list(self, client, mock_subscribe_service):
        resp = client.post("/api/v1/subscription/movie/list", json={})
        assert resp.status_code == 200
        mock_subscribe_service.get_subscribe_movies.assert_called_once()

    def test_movie_list_excludes_custom_profiles(self, client, mock_subscribe_service):
        mock_subscribe_service.get_subscribe_movies.return_value = {
            "1": {"id": 1, "content_profile": "demo"},
            "2": {"id": 2, "content_profile": "default"},
            "3": {"id": 3},
        }

        resp = client.post("/api/v1/subscription/movie/list", json={})

        assert resp.status_code == 200
        assert [item["id"] for item in resp.json()["data"]] == [2, 3]

    def test_movie_list_filters_custom_profile(self, client, mock_subscribe_service):
        mock_subscribe_service.get_subscribe_movies.return_value = {
            "1": {"id": 1, "content_profile": "demo"},
            "2": {"id": 2, "content_profile": "default"},
        }

        resp = client.post("/api/v1/subscription/movie/list", json={"content_profile": "demo"})

        assert resp.status_code == 200
        assert [item["id"] for item in resp.json()["data"]] == [1]

    def test_get_rss_history(self, client, mock_history_service):
        resp = client.post("/api/v1/subscription/history", json={"type": "movie"})
        assert resp.status_code == 200
        mock_history_service.get_history.assert_called_once()

    def test_get_tv_rss_items(self, client, mock_calendar_service):
        resp = client.post("/api/v1/subscription/tv/items", json={})
        assert resp.status_code == 200
        mock_calendar_service.get_tv_items.assert_called_once()

    def test_get_tv_rss_list(self, client, mock_subscribe_service):
        resp = client.post("/api/v1/subscription/tv/list", json={})
        assert resp.status_code == 200
        mock_subscribe_service.get_subscribe_tvs.assert_called_once()

    def test_truncate_rsshistory(self, client, mock_history_service):
        resp = client.post("/api/v1/subscription/history/clear", json={})
        assert resp.status_code == 200
        mock_history_service.truncate.assert_called_once()

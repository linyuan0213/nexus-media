"""
测试 FastAPI RSS Router
"""
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.deps import get_current_user, get_rss_subscription_service

# 绕过认证
app.dependency_overrides[get_current_user] = lambda: "testuser"
client = TestClient(app)


class TestRssRouter:
    def _mock_rss(self):
        mock_svc = MagicMock()
        app.dependency_overrides[get_rss_subscription_service] = lambda: mock_svc
        return mock_svc

    def _teardown(self):
        app.dependency_overrides.pop(get_rss_subscription_service, None)

    # ------------------------------------------------------------------
    # add_rss_media
    # ------------------------------------------------------------------
    def test_add_rss_media(self):
        mock_svc = self._mock_rss()
        mock_svc.add_rss_media.return_value = MagicMock(
            code=0, msg="添加成功", rssid="123")
        try:
            resp = client.post("/api/rss/add_rss_media", json={
                "name": "Test Movie", "year": "2024", "type": "MOV"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["rssid"] == "123"
        finally:
            self._teardown()

    def test_add_rss_media_fail(self):
        mock_svc = self._mock_rss()
        mock_svc.add_rss_media.return_value = MagicMock(
            code=-1, msg="添加失败", rssid=None)
        try:
            resp = client.post("/api/rss/add_rss_media", json={
                "name": "Test", "type": "MOV"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == -1
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # delete_rss_history
    # ------------------------------------------------------------------
    def test_delete_rss_history(self):
        mock_svc = self._mock_rss()
        try:
            resp = client.post("/api/rss/delete_rss_history", json={"rssid": "1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            mock_svc.delete_rss_history.assert_called_once_with(rssid="1")
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # re_rss_history
    # ------------------------------------------------------------------
    def test_re_rss_history(self):
        mock_svc = self._mock_rss()
        mock_svc.re_rss_history.return_value = (0, "重新订阅成功")
        try:
            resp = client.post("/api/rss/re_rss_history", json={
                "rssid": "1", "type": "MOV"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["msg"] == "重新订阅成功"
        finally:
            self._teardown()

    def test_re_rss_history_fail(self):
        mock_svc = self._mock_rss()
        mock_svc.re_rss_history.return_value = (-1, "记录不存在")
        try:
            resp = client.post("/api/rss/re_rss_history", json={
                "rssid": "1", "type": "MOV"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == -1
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # refresh_rss
    # ------------------------------------------------------------------
    def test_refresh_rss(self):
        mock_svc = self._mock_rss()
        try:
            resp = client.post("/api/rss/refresh_rss", json={
                "type": "MOV", "rssid": "1", "page": "movie"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["page"] == "movie"
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # remove_rss_media
    # ------------------------------------------------------------------
    def test_remove_rss_media(self):
        mock_svc = self._mock_rss()
        try:
            resp = client.post("/api/rss/remove_rss_media", json={
                "name": "Test", "type": "MOV", "year": "2024",
                "rssid": "1", "tmdbid": "123"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            mock_svc.remove_rss_media.assert_called_once()
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # rss_detail
    # ------------------------------------------------------------------
    def test_rss_detail(self):
        mock_svc = self._mock_rss()
        mock_svc.get_rss_detail.return_value = MagicMock(
            detail={"name": "Test"})
        try:
            resp = client.post("/api/rss/rss_detail", json={
                "rssid": "1", "rsstype": "MOV"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["detail"]["name"] == "Test"
        finally:
            self._teardown()

    def test_rss_detail_not_found(self):
        mock_svc = self._mock_rss()
        mock_svc.get_rss_detail.return_value = None
        try:
            resp = client.post("/api/rss/rss_detail", json={
                "rssid": "1", "rsstype": "MOV"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 1
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # get_default_rss_setting
    # ------------------------------------------------------------------
    def test_get_default_rss_setting(self):
        mock_svc = self._mock_rss()
        mock_svc.get_default_rss_setting.return_value = {"quality": "1080p"}
        try:
            resp = client.post("/api/rss/get_default_rss_setting", json={
                "mtype": "TV"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["data"]["quality"] == "1080p"
        finally:
            self._teardown()

    def test_get_default_rss_setting_empty(self):
        mock_svc = self._mock_rss()
        mock_svc.get_default_rss_setting.return_value = None
        try:
            resp = client.post("/api/rss/get_default_rss_setting", json={
                "mtype": "TV"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 1
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # get_ical_events
    # ------------------------------------------------------------------
    def test_get_ical_events(self):
        mock_svc = self._mock_rss()
        mock_svc.get_ical_events.return_value = [{"title": "Event1"}]
        try:
            resp = client.post("/api/rss/get_ical_events", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["result"][0]["title"] == "Event1"
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # get_movie_rss_items
    # ------------------------------------------------------------------
    def test_get_movie_rss_items(self):
        mock_svc = self._mock_rss()
        mock_svc.get_movie_rss_items.return_value = [{"id": "1"}]
        try:
            resp = client.post("/api/rss/get_movie_rss_items", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["result"][0]["id"] == "1"
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # get_movie_rss_list
    # ------------------------------------------------------------------
    def test_get_movie_rss_list(self):
        mock_svc = self._mock_rss()
        mock_svc.get_movie_rss_list.return_value = {"1": {"name": "Movie"}}
        try:
            resp = client.post("/api/rss/get_movie_rss_list", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["result"]["1"]["name"] == "Movie"
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # get_rss_history
    # ------------------------------------------------------------------
    def test_get_rss_history(self):
        mock_svc = self._mock_rss()
        mock_svc.get_rss_history.return_value = [{"name": "History"}]
        try:
            resp = client.post("/api/rss/get_rss_history", json={"type": "MOV"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["result"][0]["name"] == "History"
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # get_tv_rss_items
    # ------------------------------------------------------------------
    def test_get_tv_rss_items(self):
        mock_svc = self._mock_rss()
        mock_svc.get_tv_rss_items.return_value = [{"id": "1", "season": 1}]
        try:
            resp = client.post("/api/rss/get_tv_rss_items", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["result"][0]["season"] == 1
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # get_tv_rss_list
    # ------------------------------------------------------------------
    def test_get_tv_rss_list(self):
        mock_svc = self._mock_rss()
        mock_svc.get_tv_rss_list.return_value = {"1": {"name": "TV"}}
        try:
            resp = client.post("/api/rss/get_tv_rss_list", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["result"]["1"]["name"] == "TV"
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # truncate_rsshistory
    # ------------------------------------------------------------------
    def test_truncate_rsshistory(self):
        mock_svc = self._mock_rss()
        try:
            resp = client.post("/api/rss/truncate_rsshistory", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            mock_svc.truncate_rss_history.assert_called_once()
        finally:
            self._teardown()

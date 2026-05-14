"""
测试 FastAPI Site Router
"""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from api.deps import get_current_user, get_site_service
from api.main import app

# 绕过认证
app.dependency_overrides[get_current_user] = lambda: "testuser"
client = TestClient(app)


class TestSiteRouter:
    def _mock_site(self):
        mock_svc = MagicMock()
        app.dependency_overrides[get_site_service] = lambda: mock_svc
        return mock_svc

    def _teardown(self):
        app.dependency_overrides.pop(get_site_service, None)

    # ------------------------------------------------------------------
    # check_site_attr
    # ------------------------------------------------------------------
    def test_check_site_attr(self):
        mock_svc = self._mock_site()
        mock_svc.check_site_attr.return_value = MagicMock(site_free=True, site_2xfree=False, site_hr=True)
        try:
            resp = client.post("/api/site/check_site_attr", json={"url": "https://pt.example.com"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["site_free"] is True
            assert resp.json()["site_hr"] is True
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # get_site / del_site
    # ------------------------------------------------------------------
    def test_get_site(self):
        mock_svc = self._mock_site()
        mock_svc.get_site.return_value = MagicMock(
            site={"id": "1", "name": "PT"}, site_free=False, site_2xfree=False, site_hr=False
        )
        try:
            resp = client.post("/api/site/get_site", json={"id": "1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["site"]["name"] == "PT"
        finally:
            self._teardown()

    def test_del_site(self):
        mock_svc = self._mock_site()
        mock_svc.delete_site.return_value = 0
        try:
            resp = client.post("/api/site/del_site", json={"id": "1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # get_sites
    # ------------------------------------------------------------------
    def test_get_sites(self):
        mock_svc = self._mock_site()
        mock_svc.get_sites.return_value = [{"id": "1", "name": "PT1"}]
        try:
            resp = client.post("/api/site/get_sites", json={"rss": True})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert len(resp.json()["sites"]) == 1
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # test_site
    # ------------------------------------------------------------------
    def test_test_site(self):
        mock_svc = self._mock_site()
        mock_svc.test_site.return_value = MagicMock(flag=True, msg="测试成功", times=0.5, code=0)
        try:
            resp = client.post("/api/site/test_site", json={"id": "1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["msg"] == "测试成功"
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # update_site
    # ------------------------------------------------------------------
    def test_update_site(self):
        mock_svc = self._mock_site()
        mock_svc.update_site.return_value = MagicMock(code=0, msg="")
        try:
            resp = client.post(
                "/api/site/update_site", json={"site_id": "", "site_name": "NewPT", "site_signurl": "https://new.pt"}
            )
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # update_site_cookie_ua
    # ------------------------------------------------------------------
    def test_update_site_cookie_ua(self):
        mock_svc = self._mock_site()
        try:
            resp = client.post(
                "/api/site/update_site_cookie_ua", json={"site_id": "1", "site_cookie": "c=1", "site_ua": "ua"}
            )
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # get_site_activity / get_site_history / get_site_seeding_info
    # ------------------------------------------------------------------
    def test_get_site_activity(self):
        mock_svc = self._mock_site()
        mock_svc.get_site_activity.return_value = MagicMock(dataset=[["upload", "download"], [100, 200]])
        try:
            resp = client.post("/api/site/get_site_activity", json={"name": "PT"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["dataset"][1] == [100, 200]
        finally:
            self._teardown()

    def test_get_site_history(self):
        mock_svc = self._mock_site()
        mock_svc.get_site_history.return_value = MagicMock(dataset=[["site", "upload", "download"], ["PT", 1, 2]])
        try:
            resp = client.post("/api/site/get_site_history", json={"days": 7})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown()

    def test_get_site_seeding_info(self):
        mock_svc = self._mock_site()
        mock_svc.get_site_seeding_info.return_value = MagicMock(dataset=[["seeders", "size"], [10, "1G"]])
        try:
            resp = client.post("/api/site/get_site_seeding_info", json={"name": "PT"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # get_site_favicon
    # ------------------------------------------------------------------
    def test_get_site_favicon(self):
        mock_svc = self._mock_site()
        mock_svc.get_site_favicon.return_value = "base64data"
        try:
            resp = client.post("/api/site/get_site_favicon", json={"name": "PT"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["icon"] == "base64data"
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # set_site_captcha_code
    # ------------------------------------------------------------------
    def test_set_site_captcha_code(self):
        mock_svc = self._mock_site()
        try:
            resp = client.post("/api/site/set_site_captcha_code", json={"code": "abc", "value": "123"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # get_site_user_statistics
    # ------------------------------------------------------------------
    def test_get_site_user_statistics(self):
        mock_svc = self._mock_site()
        mock_svc.get_site_user_statistics.return_value = [{"site": "PT"}]
        try:
            resp = client.post("/api/site/get_site_user_statistics", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["data"][0]["site"] == "PT"
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # list_site_resources
    # ------------------------------------------------------------------
    def test_list_site_resources(self):
        mock_svc = self._mock_site()
        mock_svc.list_site_resources.return_value = MagicMock(success=True, data=[{"title": "Movie"}], msg="")
        try:
            resp = client.post("/api/site/list_site_resources", json={"id": "1", "page": 1, "keyword": ""})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["data"][0]["title"] == "Movie"
        finally:
            self._teardown()

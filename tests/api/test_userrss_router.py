"""
测试 FastAPI UserRss Router
"""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from api.deps import get_current_user, get_user_rss_service
from api.main import app

# 绕过认证
app.dependency_overrides[get_current_user] = lambda: "testuser"
client = TestClient(app)


class TestUserRssRouter:
    def _mock_userrss(self):
        mock_svc = MagicMock()
        app.dependency_overrides[get_user_rss_service] = lambda: mock_svc
        return mock_svc

    def _teardown(self):
        app.dependency_overrides.pop(get_user_rss_service, None)

    # ------------------------------------------------------------------
    # check_userrss_task
    # ------------------------------------------------------------------
    def test_check_userrss_task(self):
        mock_svc = self._mock_userrss()
        mock_svc.check_tasks.return_value = True
        try:
            resp = client.post("/api/userrss/tasks/check", json={"ids": [1, 2], "flag": "enable"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            mock_svc.check_tasks.assert_called_once_with(taskids=[1, 2], flag="enable")
        finally:
            self._teardown()

    def test_check_userrss_task_exception(self):
        mock_svc = self._mock_userrss()
        mock_svc.check_tasks.side_effect = Exception("boom")
        try:
            resp = client.post("/api/userrss/tasks/check", json={"ids": [1], "flag": "enable"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 1
            assert resp.json()["msg"] == "自定义订阅状态设置失败"
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # delete_rssparser
    # ------------------------------------------------------------------
    def test_delete_rssparser(self):
        mock_svc = self._mock_userrss()
        mock_svc.delete_parser.return_value = True
        try:
            resp = client.post("/api/userrss/parsers/delete", json={"id": "1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown()

    def test_delete_rssparser_fail(self):
        mock_svc = self._mock_userrss()
        mock_svc.delete_parser.return_value = False
        try:
            resp = client.post("/api/userrss/parsers/delete", json={"id": "1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 1
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # delete_userrss_task
    # ------------------------------------------------------------------
    def test_delete_userrss_task(self):
        mock_svc = self._mock_userrss()
        mock_svc.delete_task.return_value = True
        try:
            resp = client.post("/api/userrss/tasks/delete", json={"id": "1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # list_rss_parsers
    # ------------------------------------------------------------------
    def test_list_rss_parsers(self):
        mock_svc = self._mock_userrss()
        mock_svc.get_parsers.return_value = [{"id": 1}]
        try:
            resp = client.post("/api/userrss/parsers", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["parsers"][0]["id"] == 1
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # get_rssparser
    # ------------------------------------------------------------------
    def test_get_rssparser(self):
        mock_svc = self._mock_userrss()
        mock_svc.get_parser.return_value = {"name": "P1"}
        try:
            resp = client.post("/api/userrss/parsers/detail", json={"id": "1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["detail"]["name"] == "P1"
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # get_userrss_task
    # ------------------------------------------------------------------
    def test_get_userrss_task(self):
        mock_svc = self._mock_userrss()
        mock_svc.get_task.return_value = {"name": "T1"}
        try:
            resp = client.post("/api/userrss/tasks/detail", json={"id": "1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["detail"]["name"] == "T1"
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # list_rss_tasks
    # ------------------------------------------------------------------
    def test_list_rss_tasks(self):
        mock_svc = self._mock_userrss()
        mock_svc.get_tasks.return_value = [{"id": 1}]
        mock_svc.get_parsers.return_value = [{"id": 2}]
        try:
            resp = client.post("/api/userrss/tasks", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["tasks"][0]["id"] == 1
            assert resp.json()["parsers"][0]["id"] == 2
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # list_rss_articles
    # ------------------------------------------------------------------
    def test_list_rss_articles(self):
        mock_svc = self._mock_userrss()
        mock_svc.get_articles.return_value = MagicMock(articles=[{"title": "A1"}], count=1, uses=1, address_count=2)
        try:
            resp = client.post("/api/userrss/articles", json={"id": "1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["data"][0]["title"] == "A1"
        finally:
            self._teardown()

    def test_list_rss_articles_empty(self):
        mock_svc = self._mock_userrss()
        mock_svc.get_articles.return_value = MagicMock(articles=None, count=0, uses=0, address_count=0)
        try:
            resp = client.post("/api/userrss/articles", json={"id": "1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 1
            assert resp.json()["msg"] == "未获取到报文"
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # list_rss_history
    # ------------------------------------------------------------------
    def test_list_rss_history(self):
        mock_svc = self._mock_userrss()
        mock_svc.get_history.return_value = MagicMock(downloads=[{"title": "H1"}], count=1)
        try:
            resp = client.post("/api/userrss/articles/history", json={"id": "1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["data"][0]["title"] == "H1"
        finally:
            self._teardown()

    def test_list_rss_history_empty(self):
        mock_svc = self._mock_userrss()
        mock_svc.get_history.return_value = MagicMock(downloads=[], count=0)
        try:
            resp = client.post("/api/userrss/articles/history", json={"id": "1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 1
            assert resp.json()["msg"] == "无下载记录"
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # rss_article_test
    # ------------------------------------------------------------------
    def test_rss_article_test(self):
        mock_svc = self._mock_userrss()
        mock_svc.test_article.return_value = MagicMock(name="Test", media_dict={"title": "T1"})
        try:
            resp = client.post("/api/userrss/articles/test", json={"taskid": "1", "title": "Article"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["data"]["title"] == "T1"
        finally:
            self._teardown()

    def test_rss_article_test_unrecognized(self):
        mock_svc = self._mock_userrss()
        dto = MagicMock()
        dto.name = "无法识别"
        dto.media_dict = {}
        mock_svc.test_article.return_value = dto
        try:
            resp = client.post("/api/userrss/articles/test", json={"taskid": "1", "title": "Article"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["data"]["name"] == "无法识别"
        finally:
            self._teardown()

    def test_rss_article_test_missing_params(self):
        self._mock_userrss()
        try:
            resp = client.post("/api/userrss/articles/test", json={"taskid": "1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == -1
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # rss_articles_check
    # ------------------------------------------------------------------
    def test_rss_articles_check(self):
        mock_svc = self._mock_userrss()
        mock_svc.check_articles.return_value = True
        try:
            resp = client.post("/api/userrss/articles/check", json={"taskid": "1", "flag": "Y", "articles": ["a1"]})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown()

    def test_rss_articles_check_no_articles(self):
        self._mock_userrss()
        try:
            resp = client.post("/api/userrss/articles/check", json={"taskid": "1", "flag": "Y"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 2
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # rss_articles_download
    # ------------------------------------------------------------------
    def test_rss_articles_download(self):
        mock_svc = self._mock_userrss()
        mock_svc.download_articles.return_value = True
        try:
            resp = client.post("/api/userrss/articles/download", json={"taskid": "1", "articles": ["a1"]})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # run_userrss
    # ------------------------------------------------------------------
    def test_run_userrss(self):
        mock_svc = self._mock_userrss()
        try:
            resp = client.post("/api/userrss/tasks/run", json={"id": "1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            mock_svc.run_task.assert_called_once_with("1")
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # update_rssparser
    # ------------------------------------------------------------------
    def test_update_rssparser(self):
        mock_svc = self._mock_userrss()
        mock_svc.update_parser.return_value = True
        try:
            resp = client.post(
                "/api/userrss/parsers/update",
                json={"id": "1", "name": "Parser1", "type": "json", "format": "{}", "params": ""},
            )
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown()

    def test_update_rssparser_fail(self):
        mock_svc = self._mock_userrss()
        mock_svc.update_parser.return_value = False
        try:
            resp = client.post("/api/userrss/parsers/update", json={"id": "1", "name": "P1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 1
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # update_userrss_task
    # ------------------------------------------------------------------
    def test_update_userrss_task(self):
        mock_svc = self._mock_userrss()
        mock_svc.update_task.return_value = MagicMock(success=True)
        try:
            resp = client.post("/api/userrss/tasks/update", json={"data": {"name": "Task1"}})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown()

    def test_update_userrss_task_fail(self):
        mock_svc = self._mock_userrss()
        mock_svc.update_task.return_value = MagicMock(success=False)
        try:
            resp = client.post("/api/userrss/tasks/update", json={"data": {"name": "Task1"}})
            assert resp.status_code == 200
            assert resp.json()["code"] == 1
        finally:
            self._teardown()

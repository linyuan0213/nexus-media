"""
测试 FastAPI Filter Router
"""
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.deps import get_current_user
from api.main import app

# 绕过认证
app.dependency_overrides[get_current_user] = lambda: "testuser"
client = TestClient(app)


class TestFilterRouter:
    # ------------------------------------------------------------------
    # add_filtergroup
    # ------------------------------------------------------------------
    @patch("api.routers.filter.Filter")
    def test_add_filtergroup(self, mock_filter_cls):
        mock_f = MagicMock()
        mock_filter_cls.return_value = mock_f

        resp = client.post("/api/filter/add_filtergroup", json={
            "name": "Group1", "default": "Y"
        })
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        mock_f.add_group.assert_called_once_with("Group1", "Y")

    @patch("api.routers.filter.Filter")
    def test_add_filtergroup_no_name(self, mock_filter_cls):
        resp = client.post("/api/filter/add_filtergroup", json={})
        assert resp.status_code == 200
        assert resp.json()["code"] == -1

    # ------------------------------------------------------------------
    # add_filterrule
    # ------------------------------------------------------------------
    @patch("api.routers.filter.Filter")
    def test_add_filterrule(self, mock_filter_cls):
        mock_f = MagicMock()
        mock_filter_cls.return_value = mock_f

        resp = client.post("/api/filter/add_filterrule", json={
            "rule_id": 1,
            "group_id": 2,
            "rule_name": "R1",
            "rule_pri": "10",
            "rule_include": "1080p",
            "rule_exclude": "720p",
            "rule_sizelimit": "1,10",
            "rule_free": "1.0 0.0"
        })
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        mock_f.add_filter_rule.assert_called_once()

    # ------------------------------------------------------------------
    # del_filtergroup
    # ------------------------------------------------------------------
    @patch("api.routers.filter.Filter")
    def test_del_filtergroup(self, mock_filter_cls):
        mock_f = MagicMock()
        mock_filter_cls.return_value = mock_f

        resp = client.post("/api/filter/del_filtergroup", json={"id": 1})
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        mock_f.delete_filtergroup.assert_called_once_with(1)

    # ------------------------------------------------------------------
    # del_filterrule
    # ------------------------------------------------------------------
    @patch("api.routers.filter.Filter")
    def test_del_filterrule(self, mock_filter_cls):
        mock_f = MagicMock()
        mock_filter_cls.return_value = mock_f

        resp = client.post("/api/filter/del_filterrule", json={"id": 1})
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        mock_f.delete_filterrule.assert_called_once_with(1)

    # ------------------------------------------------------------------
    # filterrule_detail
    # ------------------------------------------------------------------
    @patch("api.routers.filter.Filter")
    def test_filterrule_detail(self, mock_filter_cls):
        mock_f = MagicMock()
        mock_f.get_rule_detail.return_value = {
            "id": 1, "name": "R1", "include": "a\nb"
        }
        mock_filter_cls.return_value = mock_f

        resp = client.post("/api/filter/filterrule_detail", json={
            "groupid": 1, "ruleid": 2
        })
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        assert resp.json()["info"]["name"] == "R1"

    # ------------------------------------------------------------------
    # import_filtergroup
    # ------------------------------------------------------------------
    @patch("api.routers.filter.Filter")
    def test_import_filtergroup(self, mock_filter_cls):
        mock_f = MagicMock()
        mock_f.import_filter_group.return_value = (True, "导入成功")
        mock_filter_cls.return_value = mock_f

        resp = client.post("/api/filter/import_filtergroup", json={
            "content": "eyJuYW1lIjogIkdyb3VwMSJ9"
        })
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        assert resp.json()["msg"] == "导入成功"

    @patch("api.routers.filter.Filter")
    def test_import_filtergroup_fail(self, mock_filter_cls):
        mock_f = MagicMock()
        mock_f.import_filter_group.return_value = (False, "格式错误")
        mock_filter_cls.return_value = mock_f

        resp = client.post("/api/filter/import_filtergroup", json={
            "content": "bad"
        })
        assert resp.status_code == 200
        assert resp.json()["code"] == 1
        assert resp.json()["msg"] == "格式错误"

    # ------------------------------------------------------------------
    # restore_filtergroup
    # ------------------------------------------------------------------
    @patch("api.routers.filter.Filter")
    def test_restore_filtergroup(self, mock_filter_cls):
        mock_f = MagicMock()
        mock_filter_cls.return_value = mock_f

        resp = client.post("/api/filter/restore_filtergroup", json={
            "groupids": [1, 2],
            "init_rulegroups": [{"id": 1, "sql": ["sql1"]}]
        })
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        mock_f.restore_filter_group.assert_called_once_with(
            groupids=[1, 2],
            init_rulegroups=[{"id": 1, "sql": ["sql1"]}]
        )

    # ------------------------------------------------------------------
    # rule_test
    # ------------------------------------------------------------------
    @patch("api.routers.filter.Filter")
    def test_rule_test(self, mock_filter_cls):
        mock_f = MagicMock()
        mock_f.test_rule.return_value = (True, "匹配", 10)
        mock_filter_cls.return_value = mock_f

        resp = client.post("/api/filter/rule_test", json={
            "title": "Test Movie 2024 1080p",
            "subtitle": "",
            "size": "5",
            "rulegroup": "1"
        })
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        assert resp.json()["flag"] is True
        assert resp.json()["text"] == "匹配"
        assert resp.json()["order"] == 10

    @patch("api.routers.filter.Filter")
    def test_rule_test_no_title(self, mock_filter_cls):
        resp = client.post("/api/filter/rule_test", json={})
        assert resp.status_code == 200
        assert resp.json()["code"] == -1

    # ------------------------------------------------------------------
    # set_default_filtergroup
    # ------------------------------------------------------------------
    @patch("api.routers.filter.Filter")
    def test_set_default_filtergroup(self, mock_filter_cls):
        mock_f = MagicMock()
        mock_filter_cls.return_value = mock_f

        resp = client.post("/api/filter/set_default_filtergroup", json={"id": 1})
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        mock_f.set_default_filtergroup.assert_called_once_with(1)

    @patch("api.routers.filter.Filter")
    def test_set_default_filtergroup_no_id(self, mock_filter_cls):
        resp = client.post("/api/filter/set_default_filtergroup", json={})
        assert resp.status_code == 200
        assert resp.json()["code"] == -1

    # ------------------------------------------------------------------
    # share_filtergroup
    # ------------------------------------------------------------------
    @patch("api.routers.filter.Filter")
    def test_share_filtergroup(self, mock_filter_cls):
        mock_f = MagicMock()
        mock_f.share_filter_group.return_value = (True, "", "base64str")
        mock_filter_cls.return_value = mock_f

        resp = client.post("/api/filter/share_filtergroup", json={"id": 1})
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        assert resp.json()["string"] == "base64str"

    @patch("api.routers.filter.Filter")
    def test_share_filtergroup_fail(self, mock_filter_cls):
        mock_f = MagicMock()
        mock_f.share_filter_group.return_value = (False, "不存在", "")
        mock_filter_cls.return_value = mock_f

        resp = client.post("/api/filter/share_filtergroup", json={"id": 99})
        assert resp.status_code == 200
        assert resp.json()["code"] == 1
        assert resp.json()["msg"] == "不存在"

    # ------------------------------------------------------------------
    # get_filterrules
    # ------------------------------------------------------------------
    @patch("api.routers.filter.Filter")
    @patch("api.routers.filter._get_script_path")
    def test_get_filterrules(self, mock_script_path, mock_filter_cls):
        mock_f = MagicMock()
        mock_f.get_filterrules.return_value = (
            [{"id": 1, "name": "G1"}],
            [{"id": 2, "name": "InitG1"}]
        )
        mock_filter_cls.return_value = mock_f
        mock_script_path.return_value = "/scripts"

        resp = client.post("/api/filter/get_filterrules", json={})
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        assert resp.json()["ruleGroups"][0]["name"] == "G1"
        assert resp.json()["initRules"][0]["name"] == "InitG1"

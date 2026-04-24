"""
测试 FastAPI Plugin Router（DI override 模式）
"""
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.deps import get_current_user, get_plugin_service


# 绕过认证
app.dependency_overrides[get_current_user] = lambda: "testuser"
client = TestClient(app)


class TestPluginRouter:

    def _mock_plugin(self):
        mock_svc = MagicMock()
        app.dependency_overrides[get_plugin_service] = lambda: mock_svc
        return mock_svc

    def _teardown(self):
        app.dependency_overrides.pop(get_plugin_service, None)

    # ------------------------------------------------------------------
    # update_plugin_config
    # ------------------------------------------------------------------
    def test_update_plugin_config(self):
        mock_svc = self._mock_plugin()
        try:
            resp = client.post("/api/plugin/update_plugin_config", json={
                "plugin": "plugin1", "config": {"key": "value"}
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["msg"] == "保存成功"
            mock_svc.update_plugin_config.assert_called_once()
        finally:
            self._teardown()

    def test_update_plugin_config_no_plugin(self):
        mock_svc = self._mock_plugin()
        try:
            resp = client.post("/api/plugin/update_plugin_config", json={
                "config": {"key": "value"}
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 1
            assert resp.json()["msg"] == "数据错误"
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # get_plugin_apps
    # ------------------------------------------------------------------
    def test_get_plugin_apps(self):
        mock_svc = self._mock_plugin()
        mock_svc.get_plugin_apps.return_value = MagicMock(
            plugins=[{"id": "p1"}], statistic={"total": 1})
        try:
            resp = client.post("/api/plugin/get_plugin_apps", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["result"][0]["id"] == "p1"
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # get_plugin_page
    # ------------------------------------------------------------------
    def test_get_plugin_page(self):
        mock_svc = self._mock_plugin()
        mock_svc.get_plugin_page.return_value = MagicMock(
            title="Page", content="<div></div>", func="")
        try:
            resp = client.post("/api/plugin/get_plugin_page", json={"id": "p1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["title"] == "Page"
        finally:
            self._teardown()

    def test_get_plugin_page_no_id(self):
        self._mock_plugin()
        try:
            resp = client.post("/api/plugin/get_plugin_page", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 1
            assert resp.json()["msg"] == "参数错误"
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # get_plugin_state
    # ------------------------------------------------------------------
    def test_get_plugin_state(self):
        mock_svc = self._mock_plugin()
        mock_svc.get_plugin_state.return_value = "Running"
        try:
            resp = client.post("/api/plugin/get_plugin_state", json={"id": "p1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["state"] == "Running"
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # get_plugins_conf
    # ------------------------------------------------------------------
    def test_get_plugins_conf(self):
        mock_svc = self._mock_plugin()
        mock_svc.get_plugins_conf.return_value = [{"id": "p1"}]
        try:
            resp = client.post("/api/plugin/get_plugins_conf", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["result"][0]["id"] == "p1"
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # install_plugin
    # ------------------------------------------------------------------
    def test_install_plugin(self):
        mock_svc = self._mock_plugin()
        mock_svc.install_plugin.return_value = MagicMock(
            success=True, msg="安装成功")
        try:
            resp = client.post("/api/plugin/install_plugin", json={"id": "p1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["msg"] == "安装成功"
        finally:
            self._teardown()

    def test_install_plugin_fail(self):
        mock_svc = self._mock_plugin()
        mock_svc.install_plugin.return_value = MagicMock(
            success=False, msg="安装失败")
        try:
            resp = client.post("/api/plugin/install_plugin", json={"id": "p1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == -1
            assert resp.json()["msg"] == "安装失败"
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # run_plugin_method
    # ------------------------------------------------------------------
    def test_run_plugin_method(self):
        mock_svc = self._mock_plugin()
        mock_svc.run_plugin_method.return_value = {"result": "ok"}
        try:
            resp = client.post("/api/plugin/run_plugin_method", json={
                "plugin_id": "p1", "method": "test", "data": {"a": 1}
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["result"]["result"] == "ok"
        finally:
            self._teardown()

    def test_run_plugin_method_missing_params(self):
        self._mock_plugin()
        try:
            resp = client.post("/api/plugin/run_plugin_method", json={
                "plugin_id": "p1"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 1
            assert resp.json()["msg"] == "参数错误"
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # uninstall_plugin
    # ------------------------------------------------------------------
    def test_uninstall_plugin(self):
        mock_svc = self._mock_plugin()
        mock_svc.uninstall_plugin.return_value = MagicMock(
            success=True, msg="卸载成功")
        try:
            resp = client.post("/api/plugin/uninstall_plugin", json={"id": "p1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["msg"] == "卸载成功"
        finally:
            self._teardown()

    def test_uninstall_plugin_fail(self):
        mock_svc = self._mock_plugin()
        mock_svc.uninstall_plugin.return_value = MagicMock(
            success=False, msg="卸载失败")
        try:
            resp = client.post("/api/plugin/uninstall_plugin", json={"id": "p1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == -1
            assert resp.json()["msg"] == "卸载失败"
        finally:
            self._teardown()

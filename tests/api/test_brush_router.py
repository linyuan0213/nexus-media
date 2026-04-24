"""
测试 FastAPI Brush Router（DI 工厂 mock 版本）
"""
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.deps import get_current_user, get_brush_service


# 绕过认证
app.dependency_overrides[get_current_user] = lambda: "testuser"
client = TestClient(app)


class TestBrushRouter:

    def _mock_brush(self):
        """辅助方法：创建 mock 并注册 DI override"""
        mock_svc = MagicMock()
        app.dependency_overrides[get_brush_service] = lambda: mock_svc
        return mock_svc

    def _teardown(self):
        """清理 DI override"""
        app.dependency_overrides.pop(get_brush_service, None)

    # ------------------------------------------------------------------
    # add_brushtask
    # ------------------------------------------------------------------
    def test_add_brushtask(self):
        mock_svc = self._mock_brush()
        try:
            resp = client.post("/api/brush/add_brushtask", json={
                "brushtask_name": "Task1",
                "brushtask_site": "site1",
                "brushtask_interval": 10
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            mock_svc.add_or_update_task.assert_called_once()
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # brushtask_detail
    # ------------------------------------------------------------------
    def test_brushtask_detail(self):
        mock_svc = self._mock_brush()
        mock_svc.get_task.return_value = MagicMock(task={"id": 1, "name": "T1"})
        try:
            resp = client.post("/api/brush/brushtask_detail", json={"id": 1})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["task"]["name"] == "T1"
        finally:
            self._teardown()

    def test_brushtask_detail_not_found(self):
        mock_svc = self._mock_brush()
        mock_svc.get_task.return_value = MagicMock(task=None)
        try:
            resp = client.post("/api/brush/brushtask_detail", json={"id": 99})
            assert resp.status_code == 200
            assert resp.json()["code"] == 1
            assert resp.json()["task"] == {}
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # list_brushtasks
    # ------------------------------------------------------------------
    def test_list_brushtasks(self):
        mock_svc = self._mock_brush()
        mock_svc.get_tasks.return_value = [{"id": 1}]
        try:
            resp = client.post("/api/brush/list_brushtasks", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["tasks"][0]["id"] == 1
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # del_brushtask
    # ------------------------------------------------------------------
    def test_del_brushtask(self):
        mock_svc = self._mock_brush()
        try:
            resp = client.post("/api/brush/del_brushtask", json={"id": 1})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            mock_svc.delete_task.assert_called_once_with(1)
        finally:
            self._teardown()

    def test_del_brushtask_no_id(self):
        mock_svc = self._mock_brush()
        try:
            resp = client.post("/api/brush/del_brushtask", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 1
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # list_brushtask_torrents
    # ------------------------------------------------------------------
    def test_list_brushtask_torrents(self):
        mock_svc = self._mock_brush()
        mock_svc.get_torrents.return_value = MagicMock(
            torrents=[{"name": "t1"}])
        try:
            resp = client.post("/api/brush/list_brushtask_torrents", json={"id": 1})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["data"][0]["name"] == "t1"
        finally:
            self._teardown()

    def test_list_brushtask_torrents_empty(self):
        mock_svc = self._mock_brush()
        mock_svc.get_torrents.return_value = MagicMock(torrents=None)
        try:
            resp = client.post("/api/brush/list_brushtask_torrents", json={"id": 1})
            assert resp.status_code == 200
            assert resp.json()["code"] == 1
            assert resp.json()["msg"] == "未下载种子或未获取到种子明细"
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # run_brushtask
    # ------------------------------------------------------------------
    def test_run_brushtask(self):
        mock_svc = self._mock_brush()
        try:
            resp = client.post("/api/brush/run_brushtask", json={"id": 1})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            mock_svc.run_task.assert_called_once_with(1)
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    # update_brushtask_state
    # ------------------------------------------------------------------
    def test_update_brushtask_state(self):
        mock_svc = self._mock_brush()
        try:
            resp = client.post("/api/brush/update_brushtask_state", json={
                "state": "Y", "ids": [1, 2]
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            mock_svc.update_task_state.assert_called_once_with(
                state="Y", task_ids=[1, 2])
        finally:
            self._teardown()

    def test_update_brushtask_state_exception(self):
        mock_svc = self._mock_brush()
        mock_svc.update_task_state.side_effect = Exception("boom")
        try:
            resp = client.post("/api/brush/update_brushtask_state", json={
                "state": "Y", "ids": [1]
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 1
            assert resp.json()["msg"] == "刷流任务设置失败"
        finally:
            self._teardown()

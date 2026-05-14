"""
测试 FastAPI Scheduler Router
"""
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from api.deps import get_current_user, get_scheduler_service
from api.main import app

# 绕过认证
app.dependency_overrides[get_current_user] = lambda: "testuser"
client = TestClient(app)


class TestSchedulerRouter:

    def _mock_scheduler(self):
        mock_svc = MagicMock()
        app.dependency_overrides[get_scheduler_service] = lambda: mock_svc
        return mock_svc

    def _teardown(self):
        app.dependency_overrides.pop(get_scheduler_service, None)

    def test_delete_scheduler_job(self):
        mock_svc = self._mock_scheduler()
        mock_svc.delete_job.return_value = MagicMock(code=0, msg="删除成功")
        try:
            resp = client.post("/api/scheduler/jobs/delete", json={"id": "job1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["msg"] == "删除成功"
        finally:
            self._teardown()

    def test_delete_scheduler_job_empty_id(self):
        mock_svc = self._mock_scheduler()
        try:
            resp = client.post("/api/scheduler/jobs/delete", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 1
            assert resp.json()["msg"] == "任务ID不能为空"
        finally:
            self._teardown()

    def test_delete_scheduler_job_fail(self):
        mock_svc = self._mock_scheduler()
        mock_svc.delete_job.return_value = MagicMock(code=-1, msg="任务不存在")
        try:
            resp = client.post("/api/scheduler/jobs/delete", json={"id": "job1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 1
            assert resp.json()["msg"] == "任务不存在"
        finally:
            self._teardown()

    def test_get_scheduler_jobs(self):
        mock_svc = self._mock_scheduler()
        job = MagicMock()
        job.model_dump.return_value = {"id": "job1", "name": "Test Job"}
        mock_svc.get_jobs.return_value = MagicMock(code=0, data=[job])
        try:
            resp = client.post("/api/scheduler/jobs", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["data"][0]["id"] == "job1"
        finally:
            self._teardown()

    def test_get_scheduler_jobs_not_started(self):
        mock_svc = self._mock_scheduler()
        mock_svc.get_jobs.return_value = MagicMock(code=-1, msg="调度器未启动")
        try:
            resp = client.post("/api/scheduler/jobs", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 1
            assert resp.json()["msg"] == "调度器未启动"
        finally:
            self._teardown()

    def test_pause_scheduler_job(self):
        mock_svc = self._mock_scheduler()
        mock_svc.pause_job.return_value = MagicMock(code=0, msg="暂停成功")
        try:
            resp = client.post("/api/scheduler/jobs/pause", json={"id": "job1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["msg"] == "暂停成功"
        finally:
            self._teardown()

    def test_resume_scheduler_job(self):
        mock_svc = self._mock_scheduler()
        mock_svc.resume_job.return_value = MagicMock(code=0, msg="恢复成功")
        try:
            resp = client.post("/api/scheduler/jobs/resume", json={"id": "job1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["msg"] == "恢复成功"
        finally:
            self._teardown()

    def test_run_scheduler_job(self):
        mock_svc = self._mock_scheduler()
        mock_svc.run_job.return_value = MagicMock(code=0, msg="执行成功")
        try:
            resp = client.post("/api/scheduler/jobs/run", json={"id": "job1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["msg"] == "执行成功"
        finally:
            self._teardown()

    def test_update_scheduler_job(self):
        mock_svc = self._mock_scheduler()
        mock_svc.update_job.return_value = MagicMock(code=0, msg="更新成功")
        try:
            resp = client.post("/api/scheduler/jobs/update", json={
                "id": "job1", "trigger": "interval", "seconds": 60
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["msg"] == "更新成功"
        finally:
            self._teardown()

    def test_update_scheduler_job_empty_id(self):
        mock_svc = self._mock_scheduler()
        try:
            resp = client.post("/api/scheduler/jobs/update", json={
                "trigger": "interval"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 1
            assert resp.json()["msg"] == "任务ID不能为空"
        finally:
            self._teardown()

    def test_update_scheduler_job_fail(self):
        mock_svc = self._mock_scheduler()
        mock_svc.update_job.return_value = MagicMock(code=-1, msg="更新失败")
        try:
            resp = client.post("/api/scheduler/jobs/update", json={
                "id": "job1", "trigger": "cron", "cron": "0 0 * * *"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 1
            assert resp.json()["msg"] == "更新失败"
        finally:
            self._teardown()

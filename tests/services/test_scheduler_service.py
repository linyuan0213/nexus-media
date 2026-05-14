"""
SchedulerService 纯单元测试（无需 Flask app 上下文）
"""

import datetime
from unittest.mock import MagicMock, patch

from app.schemas.scheduler import (
    DeleteSchedulerJobRequest,
    PauseSchedulerJobRequest,
    ResumeSchedulerJobRequest,
    RunSchedulerJobRequest,
    UpdateSchedulerJobRequest,
)
from app.services.scheduler_service import SchedulerService


def _make_job(job_id, name=None, next_run_time=None, trigger_type="interval", trigger_attrs=None):
    trigger_attrs = trigger_attrs or {}
    job = MagicMock()
    job.id = job_id
    job.name = name or job_id
    job.next_run_time = next_run_time
    job.args = ()
    job.kwargs = {}
    job._jobstore_alias = "default"

    trigger = MagicMock()
    if trigger_type == "interval":
        trigger.interval_length = trigger_attrs.get("seconds", 300)
    elif trigger_type == "cron":
        trigger.fields = []
    elif trigger_type == "date":
        trigger.run_date = trigger_attrs.get("run_date", datetime.datetime.now())
    job.trigger = trigger
    return job


class TestSchedulerService:
    def test_delete_job_success(self):
        scheduler = MagicMock()
        scheduler.remove_job.return_value = True
        svc = SchedulerService(scheduler=scheduler)
        resp = svc.delete_job(DeleteSchedulerJobRequest(id="test"))
        assert resp.code == 0
        assert "删除成功" in resp.msg

    def test_delete_job_failure(self):
        scheduler = MagicMock()
        scheduler.remove_job.return_value = False
        svc = SchedulerService(scheduler=scheduler)
        resp = svc.delete_job(DeleteSchedulerJobRequest(id="test"))
        assert resp.code == 1
        assert "删除失败" in resp.msg

    def test_get_jobs_success(self):
        scheduler = MagicMock()
        job = _make_job(
            "Rss.rssdownload",
            next_run_time=datetime.datetime.now(),
            trigger_type="interval",
            trigger_attrs={"seconds": 300},
        )
        scheduler.get_jobs.return_value = [job]
        scheduler.get_job_statistics.return_value = {"Rss.rssdownload": {"total_runs": 5}}

        svc = SchedulerService(scheduler=scheduler)
        resp = svc.get_jobs()
        assert resp.code == 0
        assert len(resp.data) == 1
        assert resp.data[0].id == "Rss.rssdownload"
        assert resp.data[0].trigger_type == "interval"
        assert resp.data[0].statistics["total_runs"] == 5

    def test_get_jobs_scheduler_not_running(self):
        svc = SchedulerService(scheduler=None)
        resp = svc.get_jobs()
        # 当显式传入 None 时，Service 应返回 code=1 的失败响应
        assert resp.code == 1

    def test_get_jobs_scheduler_not_running_via_fallback(self):
        # 若未注入 scheduler，回退到 Scheduler().scheduler 时可能得到 mock 对象，
        # 因此该测试仅验证显式注入 None 的行为；真实回退逻辑在集成测试中覆盖。
        svc = SchedulerService(scheduler=None)
        resp = svc.get_jobs()
        assert resp.code == 1

    def test_pause_job_success(self):
        scheduler = MagicMock()
        scheduler.pause_job.return_value = True
        svc = SchedulerService(scheduler=scheduler)
        resp = svc.pause_job(PauseSchedulerJobRequest(id="test"))
        assert resp.code == 0
        assert "暂停成功" in resp.msg

    def test_resume_job_success(self):
        scheduler = MagicMock()
        scheduler.resume_job.return_value = True
        svc = SchedulerService(scheduler=scheduler)
        resp = svc.resume_job(ResumeSchedulerJobRequest(id="test"))
        assert resp.code == 0
        assert "恢复成功" in resp.msg

    @patch("app.services.scheduler_service.ThreadHelper")
    def test_run_job_success(self, mock_thread_helper):
        scheduler = MagicMock()
        job = MagicMock()
        job.func = MagicMock()
        job.args = ()
        job.kwargs = {}
        scheduler.get_job.return_value = job
        svc = SchedulerService(scheduler=scheduler)
        resp = svc.run_job(RunSchedulerJobRequest(id="test"))
        assert resp.code == 0
        assert "任务已触发" in resp.msg
        mock_thread_helper.return_value.start_thread.assert_called_once()

    def test_run_job_not_found(self):
        scheduler = MagicMock()
        scheduler.get_job.return_value = None
        svc = SchedulerService(scheduler=scheduler)
        resp = svc.run_job(RunSchedulerJobRequest(id="not_exist"))
        assert resp.code == 1
        assert "任务不存在" in resp.msg

    def test_update_job_interval_success(self):
        scheduler = MagicMock()
        job = _make_job("Rss.rssdownload")
        scheduler.get_job.return_value = job
        svc = SchedulerService(scheduler=scheduler)
        resp = svc.update_job(UpdateSchedulerJobRequest(id="Rss.rssdownload", trigger="interval", seconds=600))
        assert resp.code == 0
        assert "修改成功" in resp.msg
        scheduler.reschedule_job.assert_called_once()

    def test_update_job_cron_success(self):
        scheduler = MagicMock()
        job = _make_job("Rss.rssdownload", trigger_type="cron")
        scheduler.get_job.return_value = job
        svc = SchedulerService(scheduler=scheduler)
        resp = svc.update_job(UpdateSchedulerJobRequest(id="Rss.rssdownload", trigger="cron", cron="*/10 * * * *"))
        assert resp.code == 0
        scheduler.reschedule_job.assert_called_once()

    def test_update_job_date_success(self):
        scheduler = MagicMock()
        job = _make_job("Rss.rssdownload", trigger_type="date")
        scheduler.get_job.return_value = job
        svc = SchedulerService(scheduler=scheduler)
        resp = svc.update_job(
            UpdateSchedulerJobRequest(id="Rss.rssdownload", trigger="date", run_date="2024-01-01T00:00:00")
        )
        assert resp.code == 0
        scheduler.reschedule_job.assert_called_once()

    def test_update_job_missing_time_params(self):
        scheduler = MagicMock()
        job = _make_job("Rss.rssdownload")
        scheduler.get_job.return_value = job
        svc = SchedulerService(scheduler=scheduler)
        resp = svc.update_job(UpdateSchedulerJobRequest(id="Rss.rssdownload", trigger="interval"))
        assert resp.code == 1
        assert "缺少时间参数" in resp.msg

    def test_update_job_not_found(self):
        scheduler = MagicMock()
        scheduler.get_job.return_value = None
        svc = SchedulerService(scheduler=scheduler)
        resp = svc.update_job(UpdateSchedulerJobRequest(id="not_exist", trigger="interval", seconds=60))
        assert resp.code == 1
        assert "任务不存在" in resp.msg

    def test_update_job_invalid_cron_expression(self):
        scheduler = MagicMock()
        job = _make_job("Rss.rssdownload", trigger_type="cron")
        scheduler.get_job.return_value = job
        svc = SchedulerService(scheduler=scheduler)
        resp = svc.update_job(UpdateSchedulerJobRequest(id="Rss.rssdownload", trigger="cron", cron="bad"))
        assert resp.code == 1
        assert "格式错误" in resp.msg

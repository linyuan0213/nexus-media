"""
调度任务 Controller 测试
测试调度任务的查询、修改、删除、暂停、恢复、立即执行功能
"""

import datetime
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask
from flask_login import AnonymousUserMixin, LoginManager


class _MockUser(AnonymousUserMixin):
    is_authenticated = True


@pytest.fixture
def app_ctx():
    app = Flask(__name__)
    app.secret_key = "test"
    lm = LoginManager(app)

    @lm.user_loader
    def _load_user(user_id):
        return _MockUser()

    with app.test_request_context():
        yield


@pytest.fixture
def scheduler_mod(app_ctx):
    # 确保 decorators 和 scheduler 模块从缓存中移除，
    # 使下面的 monkey-patch 在重新导入时生效
    import sys
    from functools import wraps

    sys.modules.pop("web.controllers.scheduler", None)
    sys.modules.pop("web.core.decorators", None)
    import web.core.decorators as dec

    dec.any_auth = lambda f: f
    dec.action_login_check = lambda f: f
    dec.parse_json_data = lambda f: wraps(f)(lambda *a, **k: f(a[0] if a else {}, *a[1:], **k))
    import web.controllers.scheduler as mod

    return mod


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


class TestSchedulerController:
    @patch("app.services.scheduler_service.SchedulerCore")
    def test_get_scheduler_jobs_success(self, mock_scheduler_cls, scheduler_mod):
        scheduler = MagicMock()
        scheduler.is_running = True
        mock_scheduler_cls.return_value = scheduler

        job = _make_job(
            "Rss.rssdownload",
            next_run_time=datetime.datetime.now(),
            trigger_type="interval",
            trigger_attrs={"seconds": 300},
        )
        scheduler.get_jobs.return_value = [job]
        scheduler.get_job_statistics.return_value = {
            "Rss.rssdownload": {"total_runs": 5, "success_count": 5, "failure_count": 0}
        }

        result = scheduler_mod._get_scheduler_jobs({})
        assert result["code"] == 0
        assert len(result["data"]) == 1
        assert result["data"][0]["id"] == "Rss.rssdownload"
        assert result["data"][0]["trigger_type"] == "interval"
        assert result["data"][0]["statistics"]["total_runs"] == 5

    @patch("app.services.scheduler_service.SchedulerCore")
    def test_get_scheduler_jobs_scheduler_not_running(self, mock_scheduler_cls, scheduler_mod):
        scheduler = MagicMock()
        scheduler.is_running = False
        mock_scheduler_cls.return_value = scheduler
        result = scheduler_mod._get_scheduler_jobs({})
        assert result["code"] == 1
        assert "调度器未启动" in result["msg"]

    @patch("app.services.scheduler_service.SchedulerCore")
    def test_update_scheduler_job_interval_success(self, mock_scheduler_cls, scheduler_mod):
        scheduler = MagicMock()
        scheduler.is_running = True
        mock_scheduler_cls.return_value = scheduler
        job = _make_job("Rss.rssdownload")
        scheduler.get_job.return_value = job

        result = scheduler_mod._update_scheduler_job({"id": "Rss.rssdownload", "trigger": "interval", "seconds": 600})
        assert result["code"] == 0
        assert "修改成功" in result["msg"]
        scheduler.reschedule_job.assert_called_once()

    @patch("app.services.scheduler_service.SchedulerCore")
    def test_update_scheduler_job_cron_success(self, mock_scheduler_cls, scheduler_mod):
        scheduler = MagicMock()
        scheduler.is_running = True
        mock_scheduler_cls.return_value = scheduler
        job = _make_job("Rss.rssdownload", trigger_type="cron")
        scheduler.get_job.return_value = job

        result = scheduler_mod._update_scheduler_job(
            {"id": "Rss.rssdownload", "trigger": "cron", "cron": "*/10 * * * *"}
        )
        assert result["code"] == 0
        scheduler.reschedule_job.assert_called_once()

    @patch("app.services.scheduler_service.SchedulerCore")
    def test_update_scheduler_job_date_success(self, mock_scheduler_cls, scheduler_mod):
        scheduler = MagicMock()
        scheduler.is_running = True
        mock_scheduler_cls.return_value = scheduler
        job = _make_job("Rss.rssdownload", trigger_type="date")
        scheduler.get_job.return_value = job

        run_date = datetime.datetime.now().isoformat()
        result = scheduler_mod._update_scheduler_job({"id": "Rss.rssdownload", "trigger": "date", "run_date": run_date})
        assert result["code"] == 0
        scheduler.reschedule_job.assert_called_once()

    @patch("app.services.scheduler_service.SchedulerCore")
    def test_update_scheduler_job_missing_id(self, mock_scheduler_cls, scheduler_mod):
        result = scheduler_mod._update_scheduler_job({"trigger": "interval", "seconds": 60})
        assert result["code"] == 1
        assert "任务ID不能为空" in result["msg"]

    @patch("app.services.scheduler_service.SchedulerCore")
    def test_update_scheduler_job_not_found(self, mock_scheduler_cls, scheduler_mod):
        scheduler = MagicMock()
        scheduler.is_running = True
        mock_scheduler_cls.return_value = scheduler
        scheduler.get_job.return_value = None

        result = scheduler_mod._update_scheduler_job({"id": "not_exist", "trigger": "interval", "seconds": 60})
        assert result["code"] == 1
        assert "任务不存在" in result["msg"]

    @patch("app.services.scheduler_service.SchedulerCore")
    def test_update_scheduler_job_invalid_trigger(self, mock_scheduler_cls, scheduler_mod):
        # Pydantic DTO 会在 Controller 层直接拦截不合法的 trigger 值
        result = scheduler_mod._update_scheduler_job({"id": "Rss.rssdownload", "trigger": "unknown"})
        assert result["code"] == 1

    @patch("app.services.scheduler_service.SchedulerCore")
    def test_update_scheduler_job_unsupported_trigger(self, mock_scheduler_cls, scheduler_mod):
        # 绕过 Pydantic pattern，用合法枚举值但在 Service 层才会被拒绝的 trigger
        scheduler = MagicMock()
        scheduler.is_running = True
        mock_scheduler_cls.return_value = scheduler
        job = _make_job("Rss.rssdownload")
        scheduler.get_job.return_value = job

        result = scheduler_mod._update_scheduler_job({"id": "Rss.rssdownload", "trigger": "interval"})
        # interval 缺少 seconds/minutes/hours，Service 层返回缺少时间参数
        assert result["code"] == 1
        assert "缺少时间参数" in result["msg"]

    @patch("app.services.scheduler_service.SchedulerCore")
    def test_delete_scheduler_job_success(self, mock_scheduler_cls, scheduler_mod):
        scheduler = MagicMock()
        scheduler.is_running = True
        mock_scheduler_cls.return_value = scheduler
        scheduler.remove_job.return_value = True

        result = scheduler_mod._delete_scheduler_job({"id": "Rss.rssdownload"})
        assert result["code"] == 0
        assert "删除成功" in result["msg"]

    @patch("app.services.scheduler_service.SchedulerCore")
    def test_delete_scheduler_job_failure(self, mock_scheduler_cls, scheduler_mod):
        scheduler = MagicMock()
        scheduler.is_running = True
        mock_scheduler_cls.return_value = scheduler
        scheduler.remove_job.return_value = False

        result = scheduler_mod._delete_scheduler_job({"id": "Rss.rssdownload"})
        assert result["code"] == 1
        assert "删除失败" in result["msg"]

    @patch("app.services.scheduler_service.SchedulerCore")
    def test_pause_scheduler_job_success(self, mock_scheduler_cls, scheduler_mod):
        scheduler = MagicMock()
        scheduler.is_running = True
        mock_scheduler_cls.return_value = scheduler
        scheduler.pause_job.return_value = True

        result = scheduler_mod._pause_scheduler_job({"id": "Rss.rssdownload"})
        assert result["code"] == 0
        assert "暂停成功" in result["msg"]

    @patch("app.services.scheduler_service.SchedulerCore")
    def test_pause_scheduler_job_failure(self, mock_scheduler_cls, scheduler_mod):
        scheduler = MagicMock()
        scheduler.is_running = True
        mock_scheduler_cls.return_value = scheduler
        scheduler.pause_job.return_value = False

        result = scheduler_mod._pause_scheduler_job({"id": "Rss.rssdownload"})
        assert result["code"] == 1
        assert "暂停失败" in result["msg"]

    @patch("app.services.scheduler_service.SchedulerCore")
    def test_resume_scheduler_job_success(self, mock_scheduler_cls, scheduler_mod):
        scheduler = MagicMock()
        scheduler.is_running = True
        mock_scheduler_cls.return_value = scheduler
        scheduler.resume_job.return_value = True

        result = scheduler_mod._resume_scheduler_job({"id": "Rss.rssdownload"})
        assert result["code"] == 0
        assert "恢复成功" in result["msg"]

    @patch("app.services.scheduler_service.SchedulerCore")
    def test_resume_scheduler_job_failure(self, mock_scheduler_cls, scheduler_mod):
        scheduler = MagicMock()
        scheduler.is_running = True
        mock_scheduler_cls.return_value = scheduler
        scheduler.resume_job.return_value = False

        result = scheduler_mod._resume_scheduler_job({"id": "Rss.rssdownload"})
        assert result["code"] == 1
        assert "恢复失败" in result["msg"]

    @patch("app.services.scheduler_service.ThreadHelper")
    @patch("app.services.scheduler_service.SchedulerCore")
    def test_run_scheduler_job_success(self, mock_scheduler_cls, mock_thread_helper, scheduler_mod):
        scheduler = MagicMock()
        scheduler.is_running = True
        mock_scheduler_cls.return_value = scheduler
        job = MagicMock()
        job.func = MagicMock()
        job.args = (1, 2)
        job.kwargs = {"key": "value"}
        scheduler.get_job.return_value = job

        result = scheduler_mod._run_scheduler_job({"id": "Rss.rssdownload"})
        assert result["code"] == 0
        assert "任务已触发" in result["msg"]
        mock_thread_helper.return_value.start_thread.assert_called_once()

    @patch("app.services.scheduler_service.SchedulerCore")
    @patch("app.services.scheduler_service.ThreadHelper")
    def test_run_scheduler_job_not_found(self, mock_thread_helper, mock_scheduler_cls, scheduler_mod):
        scheduler = MagicMock()
        scheduler.is_running = True
        mock_scheduler_cls.return_value = scheduler
        scheduler.get_job.return_value = None

        result = scheduler_mod._run_scheduler_job({"id": "not_exist"})
        assert result["code"] == 1
        assert "任务不存在" in result["msg"]

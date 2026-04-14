"""
调度任务 WebAction 测试
测试调度任务的查询、修改、删除、暂停、恢复、立即执行功能
"""
import datetime
import pytest
from unittest.mock import MagicMock, patch

from web.action import WebAction


@pytest.fixture
def action():
    return WebAction()


@pytest.fixture
def mock_scheduler():
    """Mock SchedulerService 实例"""
    scheduler = MagicMock()
    return scheduler


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


class TestSchedulerWebAction:

    @patch("web.actions._scheduler.Scheduler")
    def test_get_scheduler_jobs_success(self, mock_scheduler_cls, action):
        scheduler = MagicMock()
        mock_scheduler_cls.return_value.scheduler = scheduler

        job = _make_job("Rss.rssdownload", next_run_time=datetime.datetime.now(), trigger_type="interval", trigger_attrs={"seconds": 300})
        scheduler.get_jobs.return_value = [job]
        scheduler.get_job_statistics.return_value = {
            "Rss.rssdownload": {"total_runs": 5, "success_count": 5, "failure_count": 0}
        }

        result = action.action("get_scheduler_jobs", {})
        assert result["code"] == 0
        assert len(result["data"]) == 1
        assert result["data"][0]["id"] == "Rss.rssdownload"
        assert result["data"][0]["trigger_type"] == "interval"
        assert result["data"][0]["statistics"]["total_runs"] == 5

    @patch("web.actions._scheduler.Scheduler")
    def test_get_scheduler_jobs_scheduler_not_running(self, mock_scheduler_cls, action):
        mock_scheduler_cls.return_value.scheduler = None
        result = action.action("get_scheduler_jobs", {})
        assert result["code"] == 1
        assert "调度器未启动" in result["msg"]

    @patch("web.actions._scheduler.Scheduler")
    def test_update_scheduler_job_interval_success(self, mock_scheduler_cls, action):
        scheduler = MagicMock()
        mock_scheduler_cls.return_value.scheduler = scheduler
        job = _make_job("Rss.rssdownload")
        scheduler.get_job.return_value = job
        scheduler.modify_job.return_value = True

        result = action.action("update_scheduler_job", {
            "id": "Rss.rssdownload",
            "trigger": "interval",
            "seconds": 600
        })
        assert result["code"] == 0
        assert "修改成功" in result["msg"]
        scheduler.modify_job.assert_called_once()

    @patch("web.actions._scheduler.Scheduler")
    def test_update_scheduler_job_cron_success(self, mock_scheduler_cls, action):
        scheduler = MagicMock()
        mock_scheduler_cls.return_value.scheduler = scheduler
        job = _make_job("Rss.rssdownload", trigger_type="cron")
        scheduler.get_job.return_value = job
        scheduler.modify_job.return_value = True

        result = action.action("update_scheduler_job", {
            "id": "Rss.rssdownload",
            "trigger": "cron",
            "cron": "*/10 * * * *"
        })
        assert result["code"] == 0
        scheduler.modify_job.assert_called_once()

    @patch("web.actions._scheduler.Scheduler")
    def test_update_scheduler_job_date_success(self, mock_scheduler_cls, action):
        scheduler = MagicMock()
        mock_scheduler_cls.return_value.scheduler = scheduler
        job = _make_job("Rss.rssdownload", trigger_type="date")
        scheduler.get_job.return_value = job
        scheduler.modify_job.return_value = True

        run_date = datetime.datetime.now().isoformat()
        result = action.action("update_scheduler_job", {
            "id": "Rss.rssdownload",
            "trigger": "date",
            "run_date": run_date
        })
        assert result["code"] == 0
        scheduler.modify_job.assert_called_once()

    @patch("web.actions._scheduler.Scheduler")
    def test_update_scheduler_job_missing_id(self, mock_scheduler_cls, action):
        result = action.action("update_scheduler_job", {"trigger": "interval", "seconds": 60})
        assert result["code"] == 1
        assert "任务ID不能为空" in result["msg"]

    @patch("web.actions._scheduler.Scheduler")
    def test_update_scheduler_job_not_found(self, mock_scheduler_cls, action):
        scheduler = MagicMock()
        mock_scheduler_cls.return_value.scheduler = scheduler
        scheduler.get_job.return_value = None

        result = action.action("update_scheduler_job", {
            "id": "not_exist",
            "trigger": "interval",
            "seconds": 60
        })
        assert result["code"] == 1
        assert "任务不存在" in result["msg"]

    @patch("web.actions._scheduler.Scheduler")
    def test_update_scheduler_job_invalid_trigger(self, mock_scheduler_cls, action):
        scheduler = MagicMock()
        mock_scheduler_cls.return_value.scheduler = scheduler
        job = _make_job("Rss.rssdownload")
        scheduler.get_job.return_value = job

        result = action.action("update_scheduler_job", {
            "id": "Rss.rssdownload",
            "trigger": "unknown"
        })
        assert result["code"] == 1
        assert "不支持的触发器类型" in result["msg"]

    @patch("web.actions._scheduler.Scheduler")
    def test_delete_scheduler_job_success(self, mock_scheduler_cls, action):
        scheduler = MagicMock()
        mock_scheduler_cls.return_value.scheduler = scheduler
        scheduler.remove_job.return_value = True

        result = action.action("delete_scheduler_job", {"id": "Rss.rssdownload"})
        assert result["code"] == 0
        assert "删除成功" in result["msg"]

    @patch("web.actions._scheduler.Scheduler")
    def test_delete_scheduler_job_failure(self, mock_scheduler_cls, action):
        scheduler = MagicMock()
        mock_scheduler_cls.return_value.scheduler = scheduler
        scheduler.remove_job.return_value = False

        result = action.action("delete_scheduler_job", {"id": "Rss.rssdownload"})
        assert result["code"] == 1
        assert "删除失败" in result["msg"]

    @patch("web.actions._scheduler.Scheduler")
    def test_pause_scheduler_job_success(self, mock_scheduler_cls, action):
        scheduler = MagicMock()
        mock_scheduler_cls.return_value.scheduler = scheduler
        scheduler.pause_job.return_value = True

        result = action.action("pause_scheduler_job", {"id": "Rss.rssdownload"})
        assert result["code"] == 0
        assert "暂停成功" in result["msg"]

    @patch("web.actions._scheduler.Scheduler")
    def test_pause_scheduler_job_failure(self, mock_scheduler_cls, action):
        scheduler = MagicMock()
        mock_scheduler_cls.return_value.scheduler = scheduler
        scheduler.pause_job.return_value = False

        result = action.action("pause_scheduler_job", {"id": "Rss.rssdownload"})
        assert result["code"] == 1
        assert "暂停失败" in result["msg"]

    @patch("web.actions._scheduler.Scheduler")
    def test_resume_scheduler_job_success(self, mock_scheduler_cls, action):
        scheduler = MagicMock()
        mock_scheduler_cls.return_value.scheduler = scheduler
        scheduler.resume_job.return_value = True

        result = action.action("resume_scheduler_job", {"id": "Rss.rssdownload"})
        assert result["code"] == 0
        assert "恢复成功" in result["msg"]

    @patch("web.actions._scheduler.Scheduler")
    def test_resume_scheduler_job_failure(self, mock_scheduler_cls, action):
        scheduler = MagicMock()
        mock_scheduler_cls.return_value.scheduler = scheduler
        scheduler.resume_job.return_value = False

        result = action.action("resume_scheduler_job", {"id": "Rss.rssdownload"})
        assert result["code"] == 1
        assert "恢复失败" in result["msg"]

    @patch("web.actions._scheduler.ThreadHelper")
    @patch("web.actions._scheduler.Scheduler")
    def test_run_scheduler_job_success(self, mock_scheduler_cls, mock_thread_helper, action):
        scheduler = MagicMock()
        mock_scheduler_cls.return_value.scheduler = scheduler
        job = MagicMock()
        job.func = MagicMock()
        job.args = (1, 2)
        job.kwargs = {"key": "value"}
        scheduler.get_job.return_value = job

        result = action.action("run_scheduler_job", {"id": "Rss.rssdownload"})
        assert result["code"] == 0
        assert "任务已触发" in result["msg"]
        mock_thread_helper.return_value.start_thread.assert_called_once()

    @patch("web.actions._scheduler.ThreadHelper")
    @patch("web.actions._scheduler.Scheduler")
    def test_run_scheduler_job_not_found(self, mock_scheduler_cls, mock_thread_helper, action):
        scheduler = MagicMock()
        mock_scheduler_cls.return_value.scheduler = scheduler
        scheduler.get_job.return_value = None

        result = action.action("run_scheduler_job", {"id": "not_exist"})
        assert result["code"] == 1
        assert "任务不存在" in result["msg"]

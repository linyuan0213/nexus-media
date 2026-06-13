"""Tests for app.services.scheduler package."""

import time
from unittest.mock import MagicMock, patch

import pytest
from apscheduler.events import (
    EVENT_JOB_ERROR,
    EVENT_JOB_EXECUTED,
    EVENT_JOB_MISSED,
    EVENT_JOB_SUBMITTED,
    JobExecutionEvent,
)

from app.di.registry import registry
from app.services.scheduler.core import SchedulerCore
from app.services.scheduler.event_handler import EventHandler
from app.services.scheduler.models import JobStats, JobStatus, TaskConfig


def clear_scheduler_state():
    """Helper to clear SchedulerCore state between tests."""
    try:
        registry.clear()
    except RuntimeError:
        pass


def clear_scheduler_singleton():
    """Helper to clear SchedulerCore singleton between tests."""
    from app.di.registry import registry

    registry.clear()


class TestJobStatus:
    """Test suite for JobStatus enum."""

    def test_enum_values(self):
        assert JobStatus.PENDING.value == "pending"
        assert JobStatus.RUNNING.value == "running"
        assert JobStatus.SUCCESS.value == "success"
        assert JobStatus.FAILED.value == "failed"
        assert JobStatus.RETRYING.value == "retrying"


class TestJobStats:
    """Test suite for JobStats dataclass."""

    def test_initial_state(self):
        stats = JobStats(job_id="test_job")
        assert stats.job_id == "test_job"
        assert stats.total_runs == 0
        assert stats.success_count == 0
        assert stats.failure_count == 0
        assert stats.retry_count == 0
        assert stats.consecutive_failures == 0

    def test_record_success(self):
        stats = JobStats(job_id="test_job")
        stats.record_success(duration=1.5)
        assert stats.total_runs == 1
        assert stats.success_count == 1
        assert stats.consecutive_failures == 0
        assert stats.last_duration == 1.5
        assert stats.avg_duration == 1.5

    def test_record_success_multiple(self):
        stats = JobStats(job_id="test_job")
        stats.record_success(duration=1.0)
        stats.record_success(duration=3.0)
        assert stats.total_runs == 2
        assert stats.avg_duration == 2.0

    def test_record_failure(self):
        stats = JobStats(job_id="test_job")
        stats.record_failure("timeout")
        assert stats.total_runs == 1
        assert stats.failure_count == 1
        assert stats.consecutive_failures == 1
        assert stats.last_error == "timeout"

    def test_consecutive_failures_reset_on_success(self):
        stats = JobStats(job_id="test_job")
        stats.record_failure("err1")
        stats.record_failure("err2")
        assert stats.consecutive_failures == 2
        stats.record_success(duration=1.0)
        assert stats.consecutive_failures == 0

    def test_record_retry(self):
        stats = JobStats(job_id="test_job")
        stats.record_retry()
        assert stats.retry_count == 1

    def test_to_dict(self):
        stats = JobStats(job_id="test_job")
        stats.record_success(duration=1.0)
        d = stats.to_dict()
        assert d["job_id"] == "test_job"
        assert d["total_runs"] == 1
        assert d["avg_duration"] == 1.0
        assert "last_run_time" in d


class TestTaskConfig:
    """Test suite for TaskConfig dataclass."""

    def test_default_values(self):
        def dummy():
            pass

        cfg = TaskConfig(job_id="j1", func=dummy)
        assert cfg.trigger == "interval"
        assert cfg.args == ()
        assert cfg.kwargs == {}
        assert cfg.jobstore == "default"

    def test_validate_missing_job_id(self):
        with pytest.raises(ValueError, match="job_id"):
            TaskConfig(job_id="", func=lambda: None).validate()

    def test_validate_invalid_trigger(self):
        with pytest.raises(ValueError, match="trigger"):
            TaskConfig(job_id="j1", func=lambda: None, trigger="invalid").validate()

    def test_validate_interval_no_time(self):
        with pytest.raises(ValueError, match="interval"):
            TaskConfig(job_id="j1", func=lambda: None, trigger="interval").validate()

    def test_validate_date_no_run_date(self):
        with pytest.raises(ValueError, match="run_date"):
            TaskConfig(job_id="j1", func=lambda: None, trigger="date").validate()

    def test_to_scheduler_args_interval(self):
        def dummy():
            pass

        cfg = TaskConfig(job_id="j1", func=dummy, hours=1)
        args = cfg.to_scheduler_args()
        assert args["id"] == "j1"
        assert args["trigger"] == "interval"
        assert args["hours"] == 1


class TestSchedulerCoreLifecycle:
    """Test suite for SchedulerCore lifecycle methods."""

    def setup_method(self):
        clear_scheduler_singleton()

    def teardown_method(self):
        # Ensure scheduler is stopped after each test
        try:
            core = SchedulerCore()
            if core._scheduler and core._scheduler.running:
                core._scheduler.shutdown(wait=False)
        except (KeyError, RuntimeError):
            pass
        clear_scheduler_state()

    def test_init(self):
        core = SchedulerCore()
        assert core._running is False
        assert core._scheduler is None
        assert core._job_stats == {}

    def test_is_running_false_when_not_started(self):
        core = SchedulerCore()
        assert core.is_running is False

    def test_start_service(self):
        core = SchedulerCore()
        result = core.start_service()
        assert result is True
        assert core.is_running is True
        assert core._scheduler is not None
        assert core._scheduler.running is True
        core.stop_service()

    def test_start_service_already_running(self):
        core = SchedulerCore()
        core.start_service()
        result = core.start_service()
        assert result is True  # Already running returns True
        core.stop_service()

    def test_stop_service_not_running(self):
        core = SchedulerCore()
        assert core.stop_service() is True

    def test_stop_service_running(self):
        core = SchedulerCore()
        core.start_service()
        result = core.stop_service()
        assert result is True
        assert core.is_running is False

    def test_start_service_with_load_defaults(self):
        core = SchedulerCore()
        deps = {
            "thread_executor": MagicMock(),
            "site_userinfo": MagicMock(),
            "subscription_monitor": MagicMock(),
            "media_server": MagicMock(),
            "sync_engine": MagicMock(),
            "subscribe_service": MagicMock(),
        }
        with patch("app.services.scheduler.core.load_default_jobs") as mock_load:
            core.start_service(load_defaults=True, **deps)
            mock_load.assert_called_once_with(core, **deps)
        core.stop_service()


class TestSchedulerCoreJobRegistry:
    """Test suite for SchedulerCore job registry methods."""

    def setup_method(self):
        clear_scheduler_singleton()

    def teardown_method(self):
        try:
            core = SchedulerCore()
            if core._scheduler and core._scheduler.running:
                core._scheduler.shutdown(wait=False)
        except (KeyError, RuntimeError):
            pass
        clear_scheduler_state()

    def test_start_job_no_scheduler(self):
        core = SchedulerCore()
        result = core.start_job({"job_id": "j1", "func": lambda: None, "hours": 1})
        assert result is None

    def test_start_job_success(self):
        core = SchedulerCore()
        core.start_service()
        result = core.start_job({"job_id": "j1", "func": lambda: None, "hours": 1})
        assert result is not None
        core.stop_service()

    def test_get_jobs(self):
        core = SchedulerCore()
        core.start_service()
        core.start_job({"job_id": "j1", "func": lambda: None, "hours": 1})
        jobs = core.get_jobs()
        assert len(jobs) == 1
        core.stop_service()

    def test_get_job(self):
        core = SchedulerCore()
        core.start_service()
        core.start_job({"job_id": "j1", "func": lambda: None, "hours": 1})
        job = core.get_job("j1")
        assert job is not None
        assert job.id == "j1"
        core.stop_service()

    def test_remove_job(self):
        core = SchedulerCore()
        core.start_service()
        core.start_job({"job_id": "j1", "func": lambda: None, "hours": 1})
        result = core.remove_job("j1")
        assert result is True
        assert core.get_job("j1") is None
        core.stop_service()

    def test_pause_and_resume_job(self):
        core = SchedulerCore()
        core.start_service()
        core.start_job({"job_id": "j1", "func": lambda: None, "hours": 1})

        assert core.pause_job("j1") is True
        job = core.get_job("j1")
        assert job is not None
        assert job.next_run_time is None  # paused job has no next run time

        assert core.resume_job("j1") is True
        core.stop_service()

    def test_modify_job(self):
        core = SchedulerCore()
        core.start_service()
        core.start_job({"job_id": "j1", "func": lambda: None, "hours": 1})
        result = core.modify_job("j1", name="modified")
        assert result is True
        job = core.get_job("j1")
        assert job is not None
        assert job.name == "modified"
        core.stop_service()

    def test_register_interval(self):
        core = SchedulerCore()
        core.start_service()
        job = core.register_interval("j1", lambda: None, hours=1)
        assert job is not None
        core.stop_service()

    def test_register_cron(self):
        core = SchedulerCore()
        core.start_service()
        job = core.register_cron("j1", lambda: None, cron="0 0 * * *")
        assert job is not None
        core.stop_service()

    def test_register_date(self):
        import datetime

        core = SchedulerCore()
        core.start_service()
        run_date = datetime.datetime.now() + datetime.timedelta(hours=1)
        job = core.register_date("j1", lambda: None, run_date=run_date)
        assert job is not None
        core.stop_service()

    def test_remove_all_jobs(self):
        core = SchedulerCore()
        core.start_service()
        core.start_job({"job_id": "j1", "func": lambda: None, "hours": 1})
        core.start_job({"job_id": "j2", "func": lambda: None, "hours": 1})
        assert core.remove_all_jobs() is True
        assert len(core.get_jobs()) == 0
        core.stop_service()


class TestEventHandler:
    """Test suite for EventHandler."""

    def setup_method(self):
        clear_scheduler_singleton()

    def teardown_method(self):
        try:
            core = SchedulerCore()
            if core._scheduler and core._scheduler.running:
                core._scheduler.shutdown(wait=False)
        except (KeyError, RuntimeError):
            pass
        clear_scheduler_state()

    def test_job_event_listener_submitted(self):
        core = SchedulerCore()
        handler = EventHandler(core)

        event = JobExecutionEvent(
            code=EVENT_JOB_SUBMITTED,
            job_id="j1",
            jobstore="default",
            scheduled_run_time=time.time(),
        )

        with patch("app.db.session.remove_session"):
            handler._job_event_listener(event)

        assert "j1" in core._job_start_times

    def test_handle_job_success(self):
        core = SchedulerCore()
        handler = EventHandler(core)

        core._job_start_times["j1"] = time.time() - 2.0
        event = JobExecutionEvent(
            code=EVENT_JOB_EXECUTED,
            job_id="j1",
            jobstore="default",
            scheduled_run_time=time.time(),
        )

        handler._handle_job_success("j1", event)

        assert "j1" not in core._job_start_times
        stats = core._stats_collector._get_job_stats("j1")
        assert stats.total_runs == 1
        assert stats.success_count == 1

    def test_handle_job_failure(self):
        core = SchedulerCore()
        handler = EventHandler(core)

        event = JobExecutionEvent(
            code=EVENT_JOB_ERROR,
            job_id="j1",
            jobstore="default",
            scheduled_run_time=time.time(),
            exception=ValueError("test error"),
            traceback="tb",
        )

        with patch.object(core._retry_manager, "_retry_failed_job") as mock_retry:
            handler._handle_job_failure("j1", event)

        stats = core._stats_collector._get_job_stats("j1")
        assert stats.failure_count == 1
        assert stats.last_error is not None
        assert "test error" in stats.last_error
        mock_retry.assert_called_once_with("j1")

    def test_handle_job_missed(self):
        core = SchedulerCore()
        handler = EventHandler(core)

        event = JobExecutionEvent(
            code=EVENT_JOB_MISSED,
            job_id="j1",
            jobstore="default",
            scheduled_run_time=time.time(),
        )

        # Should not raise
        handler._handle_job_missed("j1", event)


class TestRetryManager:
    """Test suite for RetryManager."""

    def setup_method(self):
        clear_scheduler_singleton()

    def teardown_method(self):
        try:
            core = SchedulerCore()
            if core._scheduler and core._scheduler.running:
                core._scheduler.shutdown(wait=False)
        except (KeyError, RuntimeError):
            pass
        clear_scheduler_state()

    def test_get_retry_key(self):
        core = SchedulerCore()
        key = core._retry_manager._get_retry_key("j1")
        assert "j1" in key

    def test_retry_count_round_trip(self):
        core = SchedulerCore()
        core._retry_manager._set_retry_count("j1", 3)
        assert core._retry_manager._get_retry_count("j1") == 3
        core._retry_manager._clear_retry_count("j1")
        assert core._retry_manager._get_retry_count("j1") == 0

    def test_retry_failed_job_max_retries(self):
        core = SchedulerCore()
        core._retry_manager._set_retry_count("j1", core.MAX_RETRY_COUNT)

        with patch("app.services.scheduler.retry_manager.log"):
            result = core._retry_manager._retry_failed_job("j1")

        assert result is False

    def test_retry_failed_job_schedules_new_job(self):
        core = SchedulerCore()
        core.start_service()
        assert core._scheduler is not None
        # Register a dummy job first so retry can find it
        core._scheduler.add_job(lambda: None, "interval", seconds=3600, id="j1")
        core._retry_manager._set_retry_count("j1", 0)

        result = core._retry_manager._retry_failed_job("j1")

        assert result is True
        # Verify a retry job was scheduled
        jobs = core._scheduler.get_jobs()
        retry_jobs = [j for j in jobs if "retry" in j.id]
        assert len(retry_jobs) == 1
        core.stop_service()


class TestStatsCollector:
    """Test suite for StatsCollector."""

    def setup_method(self):
        clear_scheduler_singleton()

    def teardown_method(self):
        try:
            core = SchedulerCore()
            if core._scheduler and core._scheduler.running:
                core._scheduler.shutdown(wait=False)
        except (KeyError, RuntimeError):
            pass
        clear_scheduler_state()

    def test_get_job_stats_creates_new(self):
        core = SchedulerCore()
        stats = core._stats_collector._get_job_stats("j1")
        assert stats.job_id == "j1"
        assert stats.total_runs == 0

    def test_get_job_statistics_single(self):
        core = SchedulerCore()
        core._stats_collector._get_job_stats("j1").record_success(1.0)
        result = core.get_job_statistics("j1")
        assert result["job_id"] == "j1"
        assert result["total_runs"] == 1

    def test_get_job_statistics_all(self):
        core = SchedulerCore()
        core._stats_collector._get_job_stats("j1").record_success(1.0)
        core._stats_collector._get_job_stats("j2").record_failure("err")
        result = core.get_job_statistics()
        assert len(result) == 2
        assert result["j1"]["total_runs"] == 1
        assert result["j2"]["failure_count"] == 1

    def test_reset_job_statistics_single(self):
        core = SchedulerCore()
        core._stats_collector._get_job_stats("j1").record_success(1.0)
        result = core.reset_job_statistics("j1")
        assert result is True
        stats = core._stats_collector._get_job_stats("j1")
        assert stats.total_runs == 0

    def test_reset_job_statistics_all(self):
        core = SchedulerCore()
        core._stats_collector._get_job_stats("j1").record_success(1.0)
        result = core.reset_job_statistics()
        assert result is True
        assert core._job_stats == {}

    def test_reset_job_statistics_not_found(self):
        core = SchedulerCore()
        result = core.reset_job_statistics("nonexistent")
        assert result is False

    def test_get_service_status(self):
        core = SchedulerCore()
        status = core.get_service_status()
        assert "running" in status
        assert "job_count" in status
        assert "jobstores" in status


class TestSchedulerCoreIntegration:
    """Integration tests for SchedulerCore facade."""

    def setup_method(self):
        clear_scheduler_singleton()

    def teardown_method(self):
        try:
            core = SchedulerCore()
            if core._scheduler and core._scheduler.running:
                core._scheduler.shutdown(wait=False)
        except (KeyError, RuntimeError):
            pass
        clear_scheduler_state()

    def test_full_lifecycle(self):
        core = SchedulerCore()

        # Start
        assert core.start_service() is True
        assert core.is_running is True

        # Register a job
        job = core.register_interval("j1", lambda: None, hours=1)
        assert job is not None

        # Get statistics
        stats = core.get_job_statistics()
        assert isinstance(stats, dict)

        # Stop
        assert core.stop_service() is True
        assert core.is_running is False

    def test_job_execution_triggers_event_handler(self):
        core = SchedulerCore()
        core.start_service()
        assert core._scheduler is not None

        # Track if event handler was called
        with patch.object(core._event_handler, "_handle_job_success") as mock_success:
            core._scheduler.add_job(lambda: None, "interval", seconds=1, id="test_evt")
            # Manually trigger event dispatch
            from apscheduler.events import EVENT_JOB_EXECUTED, JobExecutionEvent

            evt = JobExecutionEvent(EVENT_JOB_EXECUTED, "test_evt", "default", time.time(), retval=None)
            core._event_handler._job_event_listener(evt)
            mock_success.assert_called_once()

        core.stop_service()

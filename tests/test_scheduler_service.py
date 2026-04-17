"""
SchedulerCore 单元测试
验证 remove_job 对 JobLookupError 的处理
"""
import pytest
from unittest.mock import MagicMock, patch

from apscheduler.jobstores.base import JobLookupError


class TestSchedulerCoreRemoveJob:
    """测试 SchedulerCore.remove_job"""

    @patch("app.services.scheduler_core.BackgroundScheduler")
    @patch("app.services.scheduler_core.Config")
    def test_remove_job_success(self, mock_config_cls, mock_scheduler_cls):
        from app.services.scheduler_core import SchedulerCore
        # 重置单例缓存，确保每次拿到新实例
        SchedulerCore._instances.pop(SchedulerCore, None)

        mock_scheduler = MagicMock()
        mock_scheduler_cls.return_value = mock_scheduler
        mock_config_cls.return_value.get_executors.return_value = "default"

        service = SchedulerCore()
        service._scheduler = mock_scheduler

        result = service.remove_job("test_job")
        assert result is True
        mock_scheduler.remove_job.assert_called_once_with(job_id="test_job", jobstore=None)

    @patch("app.services.scheduler_core.BackgroundScheduler")
    @patch("app.services.scheduler_core.Config")
    def test_remove_job_lookup_error_returns_true(self, mock_config_cls, mock_scheduler_cls):
        """当任务不存在时，remove_job 应返回 True 且不抛异常"""
        from app.services.scheduler_core import SchedulerCore
        SchedulerCore._instances.pop(SchedulerCore, None)

        mock_scheduler = MagicMock()
        mock_scheduler.remove_job.side_effect = JobLookupError("test_job")
        mock_scheduler_cls.return_value = mock_scheduler
        mock_config_cls.return_value.get_executors.return_value = "default"

        service = SchedulerCore()
        service._scheduler = mock_scheduler

        result = service.remove_job("test_job")
        assert result is True
        mock_scheduler.remove_job.assert_called_once_with(job_id="test_job", jobstore=None)

    @patch("app.services.scheduler_core.BackgroundScheduler")
    @patch("app.services.scheduler_core.Config")
    def test_remove_job_other_exception_returns_false(self, mock_config_cls, mock_scheduler_cls):
        """当抛出非 JobLookupError 异常时，remove_job 应返回 False"""
        from app.services.scheduler_core import SchedulerCore
        SchedulerCore._instances.pop(SchedulerCore, None)

        mock_scheduler = MagicMock()
        mock_scheduler.remove_job.side_effect = RuntimeError("boom")
        mock_scheduler_cls.return_value = mock_scheduler
        mock_config_cls.return_value.get_executors.return_value = "default"

        service = SchedulerCore()
        service._scheduler = mock_scheduler

        result = service.remove_job("test_job")
        assert result is False
        mock_scheduler.remove_job.assert_called_once_with(job_id="test_job", jobstore=None)

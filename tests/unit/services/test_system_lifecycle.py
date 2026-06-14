"""SystemLifecycleService 单元测试."""

from concurrent.futures import Future
from unittest.mock import MagicMock, patch

import pytest

from app.services.system.lifecycle import SystemLifecycleService


@pytest.fixture
def lifecycle():
    executor = MagicMock()
    future = Future()
    future.set_result(None)
    executor.submit.return_value = future
    return SystemLifecycleService(
        scheduler_core=MagicMock(),
        download_monitor=MagicMock(),
        sync=MagicMock(),
        brush_task_service=MagicMock(),
        rss_checker=MagicMock(),
        torrent_remover=MagicMock(),
        downloader=MagicMock(),
        file_index_service=MagicMock(),
        thread_executor=executor,
    )


class TestSystemLifecycleService:
    @patch("app.services.system.lifecycle.check_config")
    @patch("app.services.system.lifecycle.update_config")
    @patch("app.services.system.lifecycle.check_redis")
    @patch("app.services.system.lifecycle.update_rss_state")
    @patch("app.services.system.lifecycle.init_default_categories")
    @patch("app.services.system.lifecycle.init_rbac_system")
    @patch("app.services.system.lifecycle.init_event_handlers")
    @patch("app.services.system.lifecycle.init_message_webhook_apikey")
    def test_start_service_submits_parallel_tasks(
        self,
        mock_init_message,
        mock_init_event,
        mock_init_rbac,
        mock_init_categories,
        mock_update_rss,
        mock_check_redis,
        mock_update_config,
        mock_check_config,
        lifecycle,
    ):
        lifecycle.start_service()
        assert lifecycle._thread_executor.submit.call_count == 5
        lifecycle._download_monitor.start.assert_called_once()

    @patch("app.services.system.lifecycle.HttpClient.close_all")
    @patch("app.services.system.lifecycle.AsyncHttpClient.close_all")
    def test_stop_service_submits_parallel_tasks(self, mock_async_close, mock_http_close, lifecycle):
        lifecycle.stop_service()
        assert lifecycle._thread_executor.submit.call_count == 7
        lifecycle._scheduler.stop_service.assert_called_once()

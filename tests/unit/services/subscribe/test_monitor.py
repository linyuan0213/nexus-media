"""SubscriptionMonitor 单元测试."""

from concurrent.futures import Future
from unittest.mock import MagicMock, patch

import pytest

from app.services.subscribe.monitor import SubscriptionMonitor


def _submit_wrapper():
    def _submit(func, *args, **kwargs):
        try:
            func(*args, **kwargs)
        except Exception:
            pass
        future = Future()
        future.set_result(None)
        return future

    return _submit


@pytest.fixture
def monitor():
    m = SubscriptionMonitor(
        subscribe_service=MagicMock(),
        thread_executor=MagicMock(),
        queue_strategy=MagicMock(),
        rss_strategy=MagicMock(),
        indexer_strategy=MagicMock(),
        coordinator=MagicMock(),
    )
    m._thread_executor.submit.side_effect = _submit_wrapper()  # type: ignore[attr-defined]
    return m


class TestSubscriptionMonitor:
    def test_run_all_strategies(self, monitor):
        with patch.object(monitor, "_should_run_queue", return_value=True):
            with patch.object(monitor, "_should_run_rss", return_value=True):
                with patch.object(monitor, "_should_run_search", return_value=True):
                    monitor.run()
        monitor._queue_strategy.run.assert_called_once()
        monitor._rss_strategy.run.assert_called_once()
        monitor._indexer_strategy.run.assert_called_once()

    def test_run_none(self, monitor):
        with patch.object(monitor, "_should_run_queue", return_value=False):
            with patch.object(monitor, "_should_run_rss", return_value=False):
                with patch.object(monitor, "_should_run_search", return_value=False):
                    monitor.run()
        monitor._queue_strategy.run.assert_not_called()
        monitor._rss_strategy.run.assert_not_called()
        monitor._indexer_strategy.run.assert_not_called()

    def test_run_strategy_exception(self, monitor):
        from app.core.exceptions import ServiceError

        monitor._queue_strategy.run.side_effect = ServiceError("queue error")
        with patch.object(monitor, "_should_run_queue", return_value=True):
            with patch.object(monitor, "_should_run_rss", return_value=False):
                with patch.object(monitor, "_should_run_search", return_value=False):
                    monitor.run()
        monitor._rss_strategy.run.assert_not_called()

    def test_bind_coordinator(self, monitor):
        assert monitor._queue_strategy.set_coordinator.called
        assert monitor._rss_strategy.set_coordinator.called
        assert monitor._indexer_strategy.set_coordinator.called

    def test_should_run_queue_no_config(self, monitor):
        with patch("app.services.subscribe.monitor.settings") as mock_settings:
            mock_settings.get.return_value = None
            assert monitor._should_run_queue() is True

    def test_should_run_queue_first_run(self, monitor):
        with patch("app.services.subscribe.monitor.settings") as mock_settings:
            mock_settings.get.return_value = {"queue_interval": 60}
            monitor._last_queue_run = None
            assert monitor._should_run_queue() is True

    def test_should_run_rss_disabled(self, monitor):
        with patch("app.services.subscribe.monitor.settings") as mock_settings:
            mock_settings.get.return_value = None
            assert monitor._should_run_rss() is False

    def test_should_run_rss_interval(self, monitor):
        with patch("app.services.subscribe.monitor.settings") as mock_settings:
            mock_settings.get.return_value = {"rss_interval": 10}
            mock_settings.tz = "UTC"
            assert monitor._should_run_rss() is True

    def test_should_run_search_disabled(self, monitor):
        with patch("app.services.subscribe.monitor.settings") as mock_settings:
            mock_settings.get.return_value = None
            assert monitor._should_run_search() is False

    def test_trigger(self, monitor):
        with patch.object(monitor, "run") as mock_run:
            monitor.trigger()
            mock_run.assert_called_once()

    def test_refresh_subscription_movie(self, monitor):
        monitor.refresh_subscription("movie", "123")
        monitor._thread_executor.submit.assert_called_once()

    def test_refresh_subscription_tv(self, monitor):
        monitor.refresh_subscription("tv", "456")
        monitor._thread_executor.submit.assert_called_once()

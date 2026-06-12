"""Tests for SubscriptionMonitor coordinator integration."""

from unittest.mock import MagicMock

from app.services.subscribe.coordinator import DownloadCoordinator
from app.services.subscribe.monitor import SubscriptionMonitor


class TestSubscriptionMonitorCoordinator:
    """Test suite for coordinator binding in SubscriptionMonitor."""

    def test_coordinator_bound_to_strategies(self):
        coordinator = DownloadCoordinator(lock_manager=MagicMock())
        queue_strategy = MagicMock()
        rss_strategy = MagicMock()
        indexer_strategy = MagicMock()

        monitor = SubscriptionMonitor(
            subscribe_service=MagicMock(),
            thread_executor=MagicMock(),
            queue_strategy=queue_strategy,
            rss_strategy=rss_strategy,
            indexer_strategy=indexer_strategy,
            coordinator=coordinator,
        )

        assert monitor._coordinator is coordinator
        queue_strategy.set_coordinator.assert_called_once_with(coordinator)
        rss_strategy.set_coordinator.assert_called_once_with(coordinator)
        indexer_strategy.set_coordinator.assert_called_once_with(coordinator)

    def test_no_coordinator_does_not_call_setter(self):
        queue_strategy = MagicMock()
        rss_strategy = MagicMock()
        indexer_strategy = MagicMock()

        monitor = SubscriptionMonitor(
            subscribe_service=MagicMock(),
            thread_executor=MagicMock(),
            queue_strategy=queue_strategy,
            rss_strategy=rss_strategy,
            indexer_strategy=indexer_strategy,
            coordinator=None,
        )

        assert monitor._coordinator is None
        queue_strategy.set_coordinator.assert_not_called()
        rss_strategy.set_coordinator.assert_not_called()
        indexer_strategy.set_coordinator.assert_not_called()

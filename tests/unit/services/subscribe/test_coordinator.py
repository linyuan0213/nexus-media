"""Tests for DownloadCoordinator."""

from unittest.mock import MagicMock

import pytest

from app.services.subscribe.coordinator import DownloadCoordinator


class TestDownloadCoordinator:
    """Test suite for DownloadCoordinator."""

    @pytest.fixture
    def lock_manager(self):
        return MagicMock()

    @pytest.fixture
    def coordinator(self, lock_manager):
        return DownloadCoordinator(lock_manager=lock_manager)

    @pytest.fixture
    def media_info(self):
        media = MagicMock()
        media.tmdb_id = 123
        media.get_season_string.return_value = "S01"
        return media

    def test_try_acquire_success(self, coordinator, lock_manager, media_info):
        lock = MagicMock()
        lock.acquire.return_value = True
        lock_manager.create_lock.return_value = lock

        assert coordinator.try_acquire(media_info) is True
        lock_manager.create_lock.assert_called_once_with("subscribe:download:123:S01", ttl_seconds=1800)
        lock.acquire.assert_called_once()

    def test_try_acquire_failure(self, coordinator, lock_manager, media_info):
        lock = MagicMock()
        lock.acquire.return_value = False
        lock_manager.create_lock.return_value = lock

        assert coordinator.try_acquire(media_info) is False

    def test_try_acquire_same_key_returns_true_without_new_lock(self, coordinator, lock_manager, media_info):
        lock = MagicMock()
        lock.acquire.return_value = True
        lock_manager.create_lock.return_value = lock

        assert coordinator.try_acquire(media_info) is True
        assert coordinator.try_acquire(media_info) is True
        lock_manager.create_lock.assert_called_once()

    def test_release_removes_lock(self, coordinator, lock_manager, media_info):
        lock = MagicMock()
        lock.acquire.return_value = True
        lock_manager.create_lock.return_value = lock

        coordinator.try_acquire(media_info)
        coordinator.release(media_info)

        lock.release.assert_called_once()
        assert "subscribe:download:123:S01" not in coordinator._locks

    def test_release_without_acquire_is_safe(self, coordinator, media_info):
        coordinator.release(media_info)

    def test_is_locked_true_when_held(self, coordinator, lock_manager, media_info):
        lock = MagicMock()
        lock.acquire.return_value = True
        lock_manager.create_lock.return_value = lock

        coordinator.try_acquire(media_info)
        assert coordinator.is_locked(media_info) is True

    def test_is_locked_false_when_not_held(self, coordinator, lock_manager, media_info):
        lock = MagicMock()
        lock.acquire.return_value = True
        lock_manager.create_lock.return_value = lock

        assert coordinator.is_locked(media_info) is False
        lock.release.assert_called_once()

    def test_is_locked_true_when_other_holds(self, coordinator, lock_manager, media_info):
        def side_effect(key, ttl_seconds):
            lock = MagicMock()
            lock.acquire.return_value = ttl_seconds != 1
            return lock

        lock_manager.create_lock.side_effect = side_effect

        assert coordinator.is_locked(media_info) is True

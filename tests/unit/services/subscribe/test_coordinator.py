"""Tests for app.services.subscribe.coordinator."""

from unittest.mock import MagicMock

from app.services.subscribe.coordinator import DownloadCoordinator


class _MediaInfo:
    def __init__(self, tmdb_id, season=""):
        self.tmdb_id = tmdb_id
        self._season = season

    def get_season_string(self):
        return self._season


class TestDownloadCoordinator:
    """Test suite for DownloadCoordinator."""

    def test_try_acquire_and_release(self):
        lock_manager = MagicMock()
        lock = MagicMock()
        lock.acquire.return_value = True
        lock_manager.create_lock.return_value = lock

        coord = DownloadCoordinator(lock_manager=lock_manager)
        media = _MediaInfo(123)

        assert coord.try_acquire(media) is True
        # 同实例再次尝试同 key 应该走 Redis 锁，这里 mock 仍然返回 True，
        # 但第二次 acquire 会被调用（不再做内存短路）
        assert coord.try_acquire(media) is True
        assert lock_manager.create_lock.call_count == 2
        coord.release(media)
        lock.release.assert_called_once()

    def test_release_without_acquire(self):
        lock_manager = MagicMock()
        coord = DownloadCoordinator(lock_manager=lock_manager)
        media = _MediaInfo(123)
        coord.release(media)  # 不应抛异常

    def test_acquire_fails_when_locked_by_other_instance(self):
        lock_manager = MagicMock()
        lock = MagicMock()
        lock.acquire.return_value = False
        lock_manager.create_lock.return_value = lock

        coord = DownloadCoordinator(lock_manager=lock_manager)
        media = _MediaInfo(123)

        assert coord.try_acquire(media) is False

    def test_concurrent_same_key_only_one_acquired(self):
        """模拟同 Coordinator 内多策略并发：第二次 acquire 必须失败."""
        lock_manager = MagicMock()
        lock = MagicMock()
        lock.acquire.return_value = True
        lock_manager.create_lock.return_value = lock

        coord = DownloadCoordinator(lock_manager=lock_manager)
        media = _MediaInfo(123)

        assert coord.try_acquire(media) is True
        # 模拟另一个锁对象（不同 token）无法获取
        second_lock = MagicMock()
        second_lock.acquire.return_value = False
        lock_manager.create_lock.return_value = second_lock
        assert coord.try_acquire(media) is False

"""Tests for distributed_lock package."""

from unittest.mock import MagicMock, patch

import pytest

from app.infrastructure.distributed_lock.base import LockAcquisitionError
from app.infrastructure.distributed_lock.db_lock import DbDistributedLock
from app.infrastructure.distributed_lock.lock_manager import LockManager, get_lock_manager, with_distributed_lock
from app.infrastructure.distributed_lock.redis_lock import RedisDistributedLock


class TestDistributedLockBase:
    """Test suite for DistributedLock base class."""

    def test_token_format(self):
        lock = RedisDistributedLock("test", 60)
        assert ":" in lock._token

    def test_context_manager_acquire_and_release(self):
        lock = RedisDistributedLock("test_ctx", 60)
        with (
            patch.object(lock, "acquire", return_value=True) as mock_acquire,
            patch.object(lock, "release") as mock_release,
        ):
            with lock:
                pass
            mock_acquire.assert_called_once()
            mock_release.assert_called_once()

    def test_context_manager_acquire_failure(self):
        lock = RedisDistributedLock("test_ctx_fail", 60)
        with patch.object(lock, "acquire", return_value=False):
            with pytest.raises(LockAcquisitionError):
                with lock:
                    pass


class TestRedisDistributedLock:
    """Test suite for RedisDistributedLock."""

    def test_acquire_success(self):
        mock_store = MagicMock()
        mock_client = MagicMock()
        mock_client.set.return_value = True
        mock_store._ensure_connection.return_value = mock_client

        lock = RedisDistributedLock("test_key", 60, mock_store)
        result = lock.acquire()

        assert result is True
        assert lock.owned is True
        mock_client.set.assert_called_once()

    def test_acquire_locked(self):
        mock_store = MagicMock()
        mock_client = MagicMock()
        mock_client.set.return_value = None
        mock_store._ensure_connection.return_value = mock_client

        lock = RedisDistributedLock("test_key", 60, mock_store)
        result = lock.acquire()

        assert result is False
        assert lock.owned is False

    def test_acquire_redis_unavailable(self):
        mock_store = MagicMock()
        mock_store._ensure_connection.return_value = None

        lock = RedisDistributedLock("test_key", 60, mock_store)
        result = lock.acquire()

        assert result is False

    def test_release_success(self):
        mock_store = MagicMock()
        mock_client = MagicMock()
        mock_client.eval.return_value = 1
        mock_store._ensure_connection.return_value = mock_client

        lock = RedisDistributedLock("test_key", 60, mock_store)
        lock._owned = True
        lock.release()

        assert lock.owned is False
        mock_client.eval.assert_called_once()

    def test_release_not_owned(self):
        mock_store = MagicMock()
        lock = RedisDistributedLock("test_key", 60, mock_store)
        lock.release()
        mock_store._ensure_connection.assert_not_called()

    def test_release_redis_unavailable(self):
        mock_store = MagicMock()
        mock_store._ensure_connection.return_value = None

        lock = RedisDistributedLock("test_key", 60, mock_store)
        lock._owned = True
        lock.release()

        assert lock.owned is False

    def test_extend_success(self):
        mock_store = MagicMock()
        mock_client = MagicMock()
        mock_client.eval.return_value = 1
        mock_store._ensure_connection.return_value = mock_client

        lock = RedisDistributedLock("test_key", 60, mock_store)
        lock._owned = True
        result = lock.extend(30)

        assert result is True

    def test_extend_not_owned(self):
        mock_store = MagicMock()
        lock = RedisDistributedLock("test_key", 60, mock_store)
        result = lock.extend(30)
        assert result is False


class TestDbDistributedLock:
    """Test suite for DbDistributedLock."""

    def test_acquire_success(self):
        mock_repo = MagicMock()
        mock_repo.acquire.return_value = True

        lock = DbDistributedLock("test_db_key", 60)
        with patch.object(lock, "_repo", mock_repo):
            result = lock.acquire()

        assert result is True
        assert lock.owned is True

    def test_acquire_failure(self):
        mock_repo = MagicMock()
        mock_repo.acquire.return_value = False

        lock = DbDistributedLock("test_db_key", 60)
        with patch.object(lock, "_repo", mock_repo):
            result = lock.acquire()

        assert result is False
        assert lock.owned is False

    def test_release(self):
        mock_repo = MagicMock()

        lock = DbDistributedLock("test_db_key", 60)
        lock._owned = True
        with patch.object(lock, "_repo", mock_repo):
            lock.release()

        assert lock.owned is False
        mock_repo.release.assert_called_once()

    def test_release_not_owned(self):
        mock_repo = MagicMock()

        lock = DbDistributedLock("test_db_key", 60)
        with patch.object(lock, "_repo", mock_repo):
            lock.release()

        mock_repo.release.assert_not_called()

    def test_extend(self):
        mock_repo = MagicMock()
        mock_repo.extend.return_value = True

        lock = DbDistributedLock("test_db_key", 60)
        lock._owned = True
        with patch.object(lock, "_repo", mock_repo):
            result = lock.extend(30)

        assert result is True
        mock_repo.extend.assert_called_once_with("test_db_key", lock._token, 30)


class TestLockManager:
    """Test suite for LockManager."""

    def test_create_lock_redis_available(self):
        mock_store = MagicMock()
        mock_store.is_available.return_value = True

        manager = LockManager(mock_store)
        lock = manager.create_lock("test", 60)

        assert isinstance(lock, RedisDistributedLock)

    def test_create_lock_redis_unavailable(self):
        mock_store = MagicMock()
        mock_store.is_available.return_value = False

        manager = LockManager(mock_store)
        lock = manager.create_lock("test", 60)

        assert isinstance(lock, DbDistributedLock)

    def test_is_redis_available(self):
        mock_store = MagicMock()
        mock_store.is_available.return_value = True

        manager = LockManager(mock_store)
        assert manager.is_redis_available() is True

    def test_get_lock_manager_singleton(self):
        import app.infrastructure.distributed_lock.lock_manager as lm_module

        lm_module._lock_manager = None
        lm1 = get_lock_manager()
        lm2 = get_lock_manager()
        assert lm1 is lm2


class TestWithDistributedLock:
    """Test suite for with_distributed_lock decorator."""

    def test_decorator_acquired(self):
        mock_lock = MagicMock()
        mock_lock.acquire.return_value = True

        mock_manager = MagicMock()
        mock_manager.create_lock.return_value = mock_lock

        @with_distributed_lock("lock:{func_name}", lock_manager=mock_manager)
        def my_func():
            return "done"

        result = my_func()
        assert result == "done"
        mock_lock.acquire.assert_called_once()
        mock_lock.release.assert_called_once()

    def test_decorator_skip_on_locked(self):
        mock_lock = MagicMock()
        mock_lock.acquire.return_value = False

        mock_manager = MagicMock()
        mock_manager.create_lock.return_value = mock_lock

        @with_distributed_lock("lock:{func_name}", lock_manager=mock_manager, skip_on_locked=True)
        def my_func():
            return "done"

        result = my_func()
        assert result is None
        mock_lock.acquire.assert_called_once()
        mock_lock.release.assert_not_called()

    def test_decorator_raise_on_locked(self):
        mock_lock = MagicMock()
        mock_lock.acquire.return_value = False

        mock_manager = MagicMock()
        mock_manager.create_lock.return_value = mock_lock

        @with_distributed_lock("lock:{func_name}", lock_manager=mock_manager, skip_on_locked=False)
        def my_func():
            return "done"

        with pytest.raises(LockAcquisitionError):
            my_func()

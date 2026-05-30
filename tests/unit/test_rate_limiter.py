"""速率限制器 backends 单元测试."""

from unittest.mock import MagicMock, patch

from app.infrastructure.rate_limiter.backends import MemoryBackend, RateLimiter, RedisBackend


class TestMemoryBackend:
    def test_allowed_within_limit(self):
        backend = MemoryBackend()
        for _ in range(5):
            assert backend.is_allowed("test_key", limit=5, window=60)

    def test_blocked_when_limit_reached(self):
        backend = MemoryBackend()
        for _ in range(3):
            assert backend.is_allowed("test_key", limit=3, window=60)
        assert not backend.is_allowed("test_key", limit=3, window=60)

    def test_sliding_window_expires(self):
        backend = MemoryBackend()
        backend.is_allowed("test_key", limit=2, window=0)
        assert backend.is_allowed("test_key", limit=2, window=0)

    def test_keys_are_isolated(self):
        backend = MemoryBackend()
        for _ in range(3):
            assert backend.is_allowed("key_a", limit=3, window=60)
        assert backend.is_allowed("key_b", limit=3, window=60)
        assert not backend.is_allowed("key_a", limit=3, window=60)

    def test_thread_safety(self):
        import threading

        backend = MemoryBackend()
        results = []

        def worker():
            for _ in range(10):
                results.append(backend.is_allowed("shared", limit=25, window=60))

        threads = [threading.Thread(target=worker) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results.count(True) == 25
        assert results.count(False) == 5


class TestRedisBackend:
    def test_redis_unavailable_allows_all(self):
        with patch("app.infrastructure.rate_limiter.backends.RedisStore") as mock_cls:
            mock_store = MagicMock()
            mock_store.is_available.return_value = False
            mock_cls.return_value = mock_store

            backend = RedisBackend()
            assert backend.is_allowed("test_key", limit=1, window=60)
            assert backend.is_allowed("test_key", limit=1, window=60)

    def test_redis_available_with_script(self):
        with patch("app.infrastructure.rate_limiter.backends.RedisStore") as mock_cls:
            mock_store = MagicMock()
            mock_store.is_available.return_value = True
            mock_store.script_load.return_value = "abc123"
            mock_store.evalsha.return_value = 1
            mock_cls.return_value = mock_store

            backend = RedisBackend()
            assert backend.is_allowed("test_key", limit=3, window=60)
            mock_store.evalsha.assert_called_once()
            args = mock_store.evalsha.call_args[0]
            assert args[0] == "abc123"
            assert args[1] == 1  # numkeys
            assert args[2] == "test_key"
            assert args[4] == 3  # limit

    def test_redis_blocks_when_limit_reached(self):
        with patch("app.infrastructure.rate_limiter.backends.RedisStore") as mock_cls:
            mock_store = MagicMock()
            mock_store.is_available.return_value = True
            mock_store.script_load.return_value = "abc123"
            mock_store.evalsha.return_value = 0
            mock_cls.return_value = mock_store

            backend = RedisBackend()
            assert not backend.is_allowed("test_key", limit=1, window=60)

    def test_redis_error_allows_all(self):
        with patch("app.infrastructure.rate_limiter.backends.RedisStore") as mock_cls:
            mock_store = MagicMock()
            mock_store.is_available.return_value = True
            mock_store.script_load.side_effect = RuntimeError("Redis down")
            mock_cls.return_value = mock_store

            backend = RedisBackend()
            assert backend.is_allowed("test_key", limit=1, window=60)

    def test_fallback_without_lua_script(self):
        with patch("app.infrastructure.rate_limiter.backends.RedisStore") as mock_cls:
            mock_store = MagicMock()
            mock_store.is_available.return_value = True
            mock_store.script_load.return_value = None
            mock_store.zcard.return_value = 0
            mock_store.zadd.return_value = 1
            mock_cls.return_value = mock_store

            backend = RedisBackend()
            assert backend.is_allowed("test_key", limit=3, window=60)
            mock_store.zadd.assert_called_once()


class TestRateLimiter:
    def test_chooses_redis_when_available(self):
        with patch("app.infrastructure.rate_limiter.backends.RedisStore") as mock_cls:
            mock_store = MagicMock()
            mock_store.is_available.return_value = True
            mock_store.script_load.return_value = "abc123"
            mock_store.evalsha.return_value = 1
            mock_cls.return_value = mock_store

            limiter = RateLimiter()
            assert isinstance(limiter._backend, RedisBackend)

    def test_chooses_memory_when_redis_unavailable(self):
        with patch("app.infrastructure.rate_limiter.backends.RedisStore") as mock_cls:
            mock_store = MagicMock()
            mock_store.is_available.return_value = False
            mock_cls.return_value = mock_store

            limiter = RateLimiter()
            assert isinstance(limiter._backend, MemoryBackend)

    def test_is_allowed_delegates_to_backend(self):
        with patch("app.infrastructure.rate_limiter.backends.RedisStore") as mock_cls:
            mock_store = MagicMock()
            mock_store.is_available.return_value = False
            mock_cls.return_value = mock_store

            limiter = RateLimiter()
            assert limiter.is_allowed("key", limit=5, window=60)
            for _ in range(5):
                limiter.is_allowed("key", limit=5, window=60)
            assert not limiter.is_allowed("key", limit=5, window=60)

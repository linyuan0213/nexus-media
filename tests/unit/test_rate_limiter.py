"""速率限制器 backends 单元测试."""

from unittest.mock import MagicMock, patch

from app.infrastructure.rate_limiter.backends import (
    MemorySlidingWindowBackend,
    MemoryTokenBucketBackend,
    RateLimitEngine,
    RateLimiter,
    RedisTokenBucketBackend,
)


class TestMemoryTokenBucketBackend:
    def test_allowed_within_limit(self):
        backend = MemoryTokenBucketBackend()
        for _ in range(5):
            assert backend.acquire("test_key", rate=5.0, burst=5, tokens=1, timeout=0)

    def test_blocked_when_limit_reached(self):
        backend = MemoryTokenBucketBackend()
        for _ in range(3):
            assert backend.acquire("test_key", rate=3.0, burst=3, tokens=1, timeout=0)
        assert not backend.acquire("test_key", rate=3.0, burst=3, tokens=1, timeout=0)

    def test_keys_are_isolated(self):
        backend = MemoryTokenBucketBackend()
        for _ in range(3):
            assert backend.acquire("key_a", rate=3.0, burst=3, tokens=1, timeout=0)
        assert backend.acquire("key_b", rate=3.0, burst=3, tokens=1, timeout=0)
        assert not backend.acquire("key_a", rate=3.0, burst=3, tokens=1, timeout=0)

    def test_thread_safety(self):
        import threading

        backend = MemoryTokenBucketBackend()
        results = []

        def worker():
            for _ in range(10):
                results.append(backend.acquire("shared", rate=25.0, burst=25, tokens=1, timeout=0))

        threads = [threading.Thread(target=worker) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results.count(True) == 25
        assert results.count(False) == 5


class TestMemorySlidingWindowBackend:
    def test_allowed_within_limit(self):
        backend = MemorySlidingWindowBackend()
        for _ in range(5):
            assert backend.acquire("test_key", rate=5.0, burst=5, tokens=1, timeout=0)

    def test_blocked_when_limit_reached(self):
        backend = MemorySlidingWindowBackend()
        for _ in range(3):
            assert backend.acquire("test_key", rate=3.0, burst=3, tokens=1, timeout=0)
        assert not backend.acquire("test_key", rate=3.0, burst=3, tokens=1, timeout=0)


class TestRedisTokenBucketBackend:
    def test_redis_unavailable_allows_all(self):
        with patch("app.infrastructure.rate_limiter.backends.RedisStore") as mock_cls:
            mock_store = MagicMock()
            mock_store.is_available.return_value = False
            mock_cls.return_value = mock_store

            backend = RedisTokenBucketBackend()
            assert backend.acquire("test_key", rate=1.0, burst=1, tokens=1, timeout=0)
            assert backend.acquire("test_key", rate=1.0, burst=1, tokens=1, timeout=0)

    def test_redis_available_with_script(self):
        with patch("app.infrastructure.rate_limiter.backends.RedisStore") as mock_cls:
            mock_store = MagicMock()
            mock_store.is_available.return_value = True
            mock_store.script_load.return_value = "abc123"
            mock_store.evalsha.return_value = 1
            mock_cls.return_value = mock_store

            backend = RedisTokenBucketBackend()
            assert backend.acquire("test_key", rate=3.0, burst=3, tokens=1, timeout=0)
            mock_store.evalsha.assert_called_once()
            args = mock_store.evalsha.call_args[0]
            assert args[0] == "abc123"
            assert args[1] == 1  # numkeys

    def test_redis_error_allows_all(self):
        with patch("app.infrastructure.rate_limiter.backends.RedisStore") as mock_cls:
            mock_store = MagicMock()
            mock_store.is_available.return_value = True
            mock_store.script_load.side_effect = RuntimeError("Redis down")
            mock_cls.return_value = mock_store

            backend = RedisTokenBucketBackend()
            assert backend.acquire("test_key", rate=1.0, burst=1, tokens=1, timeout=0)


class TestRateLimitEngine:
    def test_acquire_token_bucket(self):
        engine = RateLimitEngine(algorithm="token_bucket")
        for _ in range(5):
            assert engine.acquire("key", rate="5/m", burst=5, timeout=0)
        assert not engine.acquire("key", rate="5/m", burst=5, timeout=0)

    def test_try_acquire(self):
        engine = RateLimitEngine()
        assert engine.try_acquire("key", rate="10/m")

    def test_get_status(self):
        engine = RateLimitEngine()
        engine.acquire("key1", rate="10/m", timeout=0)
        status = engine.get_status("key1")
        assert "tokens" in status or "count" in status


class TestRateLimiter:
    def test_is_allowed_delegates_to_backend(self):
        limiter = RateLimiter()
        assert limiter.is_allowed("key", limit=5, window=60)
        for _ in range(5):
            limiter.is_allowed("key", limit=5, window=60)
        assert not limiter.is_allowed("key", limit=5, window=60)

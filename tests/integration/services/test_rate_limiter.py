"""Tests for app.infrastructure.rate_limiter and app.services.site_rate_limiter."""

from unittest.mock import MagicMock, patch

from app.infrastructure.rate_limiter import RateLimitEngine, rate_limit, rate_limited
from app.infrastructure.rate_limiter.backends import (
    MemorySlidingWindowBackend,
    MemoryTokenBucketBackend,
    RedisTokenBucketBackend,
    _parse_rate,
)
from app.infrastructure.rate_limiter.monitor import RateLimitMonitor
from app.services.site_rate_limiter import SiteRateLimiterService


class TestParseRate:
    def test_parse_per_minute(self):
        count, window = _parse_rate("10/m")
        assert count == 10
        assert window == 60

    def test_parse_per_second(self):
        count, window = _parse_rate("2.5/s")
        assert count == 2.5
        assert window == 1

    def test_parse_per_hour(self):
        count, window = _parse_rate("100/h")
        assert count == 100
        assert window == 3600

    def test_parse_per_day(self):
        count, window = _parse_rate("1000/d")
        assert count == 1000
        assert window == 86400

    def test_invalid_format_raises(self):
        try:
            _parse_rate("invalid")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass


class TestMemoryTokenBucketBackend:
    def test_acquire_success(self):
        backend = MemoryTokenBucketBackend()
        assert backend.acquire("key", rate=10.0, burst=10, tokens=1, timeout=0)

    def test_acquire_blocked_when_empty(self):
        backend = MemoryTokenBucketBackend()
        for _ in range(10):
            assert backend.acquire("key", rate=10.0, burst=10, tokens=1, timeout=0)
        assert not backend.acquire("key", rate=10.0, burst=10, tokens=1, timeout=0)

    def test_acquire_with_wait(self):
        backend = MemoryTokenBucketBackend()
        # Empty the bucket
        for _ in range(10):
            backend.acquire("key", rate=100.0, burst=10, tokens=1, timeout=0)
        # Should wait and refill
        assert backend.acquire("key", rate=100.0, burst=10, tokens=1, timeout=1)

    def test_acquire_timeout(self):
        backend = MemoryTokenBucketBackend()
        for _ in range(10):
            backend.acquire("key", rate=0.1, burst=10, tokens=1, timeout=0)
        # Rate is very low, should timeout
        assert not backend.acquire("key", rate=0.1, burst=10, tokens=1, timeout=0.01)

    def test_get_status(self):
        backend = MemoryTokenBucketBackend()
        backend.acquire("key1", rate=10.0, burst=10, tokens=1, timeout=0)
        status = backend.get_status("key1")
        assert "tokens" in status
        assert "blocked" in status

    def test_get_status_all_keys(self):
        backend = MemoryTokenBucketBackend()
        backend.acquire("key1", rate=10.0, burst=10, tokens=1, timeout=0)
        backend.acquire("key2", rate=10.0, burst=10, tokens=1, timeout=0)
        status = backend.get_status()
        assert "key1" in status
        assert "key2" in status


class TestMemorySlidingWindowBackend:
    def test_acquire_success(self):
        backend = MemorySlidingWindowBackend()
        for _ in range(5):
            assert backend.acquire("key", rate=5.0, burst=5, tokens=1, timeout=0)

    def test_acquire_blocked(self):
        backend = MemorySlidingWindowBackend()
        for _ in range(5):
            assert backend.acquire("key", rate=5.0, burst=5, tokens=1, timeout=0)
        assert not backend.acquire("key", rate=5.0, burst=5, tokens=1, timeout=0)

    def test_acquire_with_multiple_tokens(self):
        backend = MemorySlidingWindowBackend()
        assert backend.acquire("key", rate=5.0, burst=5, tokens=3, timeout=0)
        assert backend.acquire("key", rate=5.0, burst=5, tokens=2, timeout=0)
        assert not backend.acquire("key", rate=5.0, burst=5, tokens=1, timeout=0)

    def test_window_expires(self):
        backend = MemorySlidingWindowBackend()
        assert backend.acquire("key", rate=1000.0, burst=1, tokens=1, timeout=0)
        assert not backend.acquire("key", rate=1000.0, burst=1, tokens=1, timeout=0)


class TestRedisTokenBucketBackend:
    def test_redis_unavailable_allows_all(self):
        with patch("app.infrastructure.rate_limiter.backends.RedisStore") as mock_cls:
            mock_store = MagicMock()
            mock_store.is_available.return_value = False
            mock_cls.return_value = mock_store
            backend = RedisTokenBucketBackend()
            assert backend.acquire("key", rate=1.0, burst=1, tokens=1, timeout=0)

    def test_redis_available_with_script(self):
        with patch("app.infrastructure.rate_limiter.backends.RedisStore") as mock_cls:
            mock_store = MagicMock()
            mock_store.is_available.return_value = True
            mock_store.script_load.return_value = "sha123"
            mock_store.evalsha.return_value = 1
            mock_cls.return_value = mock_store
            backend = RedisTokenBucketBackend()
            assert backend.acquire("key", rate=1.0, burst=1, tokens=1, timeout=0)
            mock_store.evalsha.assert_called_once()

    def test_redis_error_allows_all(self):
        with patch("app.infrastructure.rate_limiter.backends.RedisStore") as mock_cls:
            mock_store = MagicMock()
            mock_store.is_available.return_value = True
            mock_store.script_load.side_effect = RuntimeError("Redis down")
            mock_cls.return_value = mock_store
            backend = RedisTokenBucketBackend()
            assert backend.acquire("key", rate=1.0, burst=1, tokens=1, timeout=0)


class TestRateLimitEngine:
    def test_token_bucket_algorithm(self):
        engine = RateLimitEngine(algorithm="token_bucket")
        for _ in range(5):
            assert engine.acquire("key", rate="5/m", burst=5, timeout=0)
        assert not engine.acquire("key", rate="5/m", burst=5, timeout=0)

    def test_sliding_window_algorithm(self):
        engine = RateLimitEngine(algorithm="sliding_window")
        for _ in range(5):
            assert engine.acquire("key", rate="5/m", burst=5, timeout=0)
        assert not engine.acquire("key", rate="5/m", burst=5, timeout=0)

    def test_try_acquire(self):
        engine = RateLimitEngine()
        assert engine.try_acquire("key", rate="10/m")

    def test_try_acquire_blocked(self):
        engine = RateLimitEngine()
        for _ in range(10):
            engine.acquire("key", rate="10/m", timeout=0)
        assert not engine.try_acquire("key", rate="10/m")

    def test_default_burst_from_rate(self):
        engine = RateLimitEngine()
        assert engine.acquire("key", rate="10/m", timeout=0)

    def test_get_status_empty(self):
        engine = RateLimitEngine()
        assert engine.get_status() == {}

    def test_get_status_after_acquire(self):
        engine = RateLimitEngine()
        engine.acquire("key", rate="10/m", timeout=0)
        status = engine.get_status("key")
        assert status is not None


class TestRateLimitMonitor:
    def test_record_success(self):
        monitor = RateLimitMonitor()
        monitor.record("key", acquired=True)
        stats = monitor.get_stats("key")
        assert stats["total"] == 1
        assert stats["blocked"] == 0

    def test_record_blocked(self):
        monitor = RateLimitMonitor()
        monitor.record("key", acquired=False)
        stats = monitor.get_stats("key")
        assert stats["total"] == 1
        assert stats["blocked"] == 1

    def test_record_waited(self):
        monitor = RateLimitMonitor()
        monitor.record("key", acquired=True, wait_time=0.5)
        stats = monitor.get_stats("key")
        assert stats["waited"] == 1
        assert stats["total_wait"] == 0.5

    def test_get_stats_all(self):
        monitor = RateLimitMonitor()
        monitor.record("key1", acquired=True)
        monitor.record("key2", acquired=False)
        stats = monitor.get_stats()
        assert "key1" in stats
        assert "key2" in stats

    def test_reset_single_key(self):
        monitor = RateLimitMonitor()
        monitor.record("key1", acquired=True)
        monitor.record("key2", acquired=True)
        monitor.reset("key1")
        assert monitor.get_stats("key1") == {}
        assert monitor.get_stats("key2") != {}

    def test_reset_all(self):
        monitor = RateLimitMonitor()
        monitor.record("key", acquired=True)
        monitor.reset()
        assert monitor.get_stats() == {}


class TestRateLimitDecorator:
    def test_rate_limited_allows_within_limit(self):
        @rate_limited(rate="10/m", timeout=0)
        def my_func():
            return "ok"

        assert my_func() == "ok"

    def test_rate_limited_blocks_over_limit(self):
        @rate_limited(rate="1/m", timeout=0)
        def my_func():
            return "ok"

        my_func()
        try:
            my_func()
            assert False, "Should have raised RuntimeError"
        except RuntimeError as e:
            assert "Rate limit exceeded" in str(e)

    def test_rate_limit_context_manager(self):
        engine = RateLimitEngine()
        with rate_limit(engine, "key", rate="10/m", timeout=0):
            pass

    def test_rate_limit_context_manager_blocks(self):
        engine = RateLimitEngine()
        for _ in range(5):
            engine.acquire("key", rate="5/m", timeout=0)
        try:
            with rate_limit(engine, "key", rate="5/m", timeout=0):
                pass
            assert False, "Should have raised RuntimeError"
        except RuntimeError as e:
            assert "Rate limit exceeded" in str(e)


class TestSiteRateLimiterService:
    def test_register_site_new_format(self):
        svc = SiteRateLimiterService(engine=RateLimitEngine())
        svc.register_site("1", {"rate_limit": "10/m", "rate_burst": 10})
        assert not svc.check("1", timeout=0)  # First call should not trigger

    def test_register_site_old_format(self):
        svc = SiteRateLimiterService(engine=RateLimitEngine())
        svc.register_site("1", {"limit_interval": 60, "limit_count": 10})
        assert not svc.check("1", timeout=0)

    def test_register_site_no_config(self):
        svc = SiteRateLimiterService(engine=RateLimitEngine())
        svc.register_site("1", {})
        assert not svc.check("1", timeout=0)

    def test_check_blocks_when_over_limit(self):
        svc = SiteRateLimiterService(engine=RateLimitEngine())
        svc.register_site("1", {"rate_limit": "2/m", "rate_burst": 2})
        assert not svc.check("1", timeout=0)
        assert not svc.check("1", timeout=0)
        assert svc.check("1", timeout=0)

    def test_get_status(self):
        svc = SiteRateLimiterService(engine=RateLimitEngine())
        svc.register_site("1", {"rate_limit": "10/m"})
        svc.check("1", timeout=0)
        status = svc.get_status("1")
        assert status is not None

    def test_register_site_json_string(self):
        svc = SiteRateLimiterService(engine=RateLimitEngine())
        svc.register_site("1", '{"rate_limit": "5/m"}')
        assert not svc.check("1", timeout=0)

    def test_register_site_invalid_json(self):
        svc = SiteRateLimiterService(engine=RateLimitEngine())
        svc.register_site("1", "invalid json")
        assert not svc.check("1", timeout=0)

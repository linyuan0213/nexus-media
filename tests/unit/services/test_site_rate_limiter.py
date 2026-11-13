"""SiteRateLimiterService 单元测试."""

from unittest.mock import MagicMock

from app.services.site_rate_limiter import SiteRateLimiterService


class TestSiteRateLimiterServiceRegister:
    def test_register_site_with_string_rate_limit(self):
        engine = MagicMock()
        engine.acquire.return_value = True
        svc = SiteRateLimiterService(engine=engine)
        svc.register_site("yema", {"rate_limit": "10/m", "rate_burst": "10"})
        config = svc.get_rate("yema")
        assert config is not None
        rate, burst = config
        assert rate == "10/m"
        assert burst == 10
        assert svc.check("yema") is False
        engine.acquire.assert_called_once()

    def test_register_site_with_old_string_format(self):
        engine = MagicMock()
        engine.acquire.return_value = True
        svc = SiteRateLimiterService(engine=engine)
        svc.register_site("zmpt", {"limit_interval": "60", "limit_count": "10"})
        config = svc.get_rate("zmpt")
        assert config is not None
        rate, burst = config
        assert rate == "10/60s"
        assert burst == 10
        assert svc.check("zmpt") is False

    def test_register_site_with_numeric_values(self):
        engine = MagicMock()
        engine.acquire.return_value = True
        svc = SiteRateLimiterService(engine=engine)
        svc.register_site("mteam", {"rate_limit": "5/s", "rate_burst": 5})
        config = svc.get_rate("mteam")
        assert config is not None
        rate, burst = config
        assert rate == "5/s"
        assert burst == 5

    def test_register_site_uses_default_when_unconfigured(self):
        engine = MagicMock()
        svc = SiteRateLimiterService(engine=engine)
        svc.register_site("none", {})
        assert svc.get_rate("none") == ("10/m", 10)

    def test_register_site_explicit_none_disables_limit(self):
        engine = MagicMock()
        svc = SiteRateLimiterService(engine=engine)
        svc.register_site("none", {"rate_limit": "none"})
        assert svc.get_rate("none") is None
        assert svc.check("none") is False
        engine.acquire.assert_not_called()

    def test_check_rate_limit_hit(self):
        engine = MagicMock()
        engine.acquire.return_value = False
        svc = SiteRateLimiterService(engine=engine)
        svc.register_site("hit", {"rate_limit": "1/m"})
        assert svc.check("hit") is True

    def test_register_site_invalid_values_use_default(self):
        svc = SiteRateLimiterService()
        svc.register_site("bad", {"limit_interval": "abc", "limit_count": "xyz"})
        assert svc.get_rate("bad") == ("10/m", 10)


class TestSiteRateLimiterConfigChange:
    def _service(self):
        from app.infrastructure.rate_limiter import MemoryTokenBucketBackend, RateLimitEngine

        return SiteRateLimiterService(engine=RateLimitEngine(backend=MemoryTokenBucketBackend()))

    def test_burst_change_resets_tokens_to_new_capacity(self):
        svc = self._service()
        svc.register_site("1", {"rate_limit": "10/m", "rate_burst": 5})
        assert svc.check("1") is False
        assert svc.get_status("1")["tokens"] < 5

        svc.register_site("1", {"rate_limit": "10/m", "rate_burst": 8})
        status = svc.get_status("1")
        assert status["burst"] == 8
        assert status["tokens"] == 8

    def test_same_config_does_not_reset_tokens(self):
        svc = self._service()
        svc.register_site("1", {"rate_limit": "10/m", "rate_burst": 5})
        assert svc.check("1") is False
        before = svc.get_status("1")["tokens"]

        svc.register_site("1", {"rate_limit": "10/m", "rate_burst": 5})
        after = svc.get_status("1")["tokens"]
        assert after <= before

    def test_stale_persistent_bucket_is_corrected_on_first_register(self):
        from app.infrastructure.rate_limiter import MemoryTokenBucketBackend, RateLimitEngine

        engine = RateLimitEngine(backend=MemoryTokenBucketBackend())
        engine.acquire("site:1", rate="10/m", burst=5, tokens=1, timeout=0)
        svc = SiteRateLimiterService(engine=engine)

        svc.register_site("1", {"rate_limit": "10/m", "rate_burst": 8})
        status = svc.get_status("1")
        assert status["burst"] == 8
        assert status["tokens"] == 8

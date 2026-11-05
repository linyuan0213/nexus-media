"""限流错误识别与指数退避."""

from app.media.metadata.errors import ProviderRateLimited
from app.services.subscribe.retry_policy import backoff_seconds, is_rate_limited


class TestSubscriberRetryPolicy:
    def test_provider_rate_limited(self):
        assert is_rate_limited(ProviderRateLimited("douban", "too many requests"))

    def test_http_429_message(self):
        assert is_rate_limited(RuntimeError("HTTP 429 Too Many Requests"))

    def test_chinese_rate_limit_message(self):
        assert is_rate_limited(RuntimeError("请求过于频繁，请稍后再试"))

    def test_other_error_not_rate_limited(self):
        assert not is_rate_limited(RuntimeError("timeout"))

    def test_exponential_backoff(self):
        assert backoff_seconds(1) == 60
        assert backoff_seconds(2) == 120
        assert backoff_seconds(3) == 240
        assert backoff_seconds(20) == 3600

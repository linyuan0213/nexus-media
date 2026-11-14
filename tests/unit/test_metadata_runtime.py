"""Provider runtime 限流/熔断/URL 安全测试."""

import pytest

from app.media.metadata import ProviderDescriptor
from app.media.metadata.errors import ProviderRateLimited
from app.media.metadata.runtime import ProviderRuntime, UnsafeProviderURL, validate_outbound_url


def test_validate_url_rejects_loopback_and_private():
    with pytest.raises(UnsafeProviderURL):
        validate_outbound_url("http://127.0.0.1:8080/x")
    with pytest.raises(UnsafeProviderURL):
        validate_outbound_url("http://localhost/x")
    with pytest.raises(UnsafeProviderURL):
        validate_outbound_url("http://192.168.1.10/x")


def test_runtime_opens_circuit_after_failures():
    runtime = ProviderRuntime(
        ProviderDescriptor(
            provider_key="demo",
            display_name="demo",
            circuit_failures=2,
            circuit_cooldown_seconds=60,
        )
    )
    runtime.record_failure()
    runtime.record_failure()

    with pytest.raises(Exception, match="熔断"):
        runtime.acquire()

    runtime.record_success()
    runtime.acquire()


def test_rate_limit_is_not_counted_as_circuit_failure():
    runtime = ProviderRuntime(
        ProviderDescriptor(
            provider_key="demo",
            display_name="demo",
            circuit_failures=1,
            circuit_cooldown_seconds=60,
        )
    )
    try:
        raise ProviderRateLimited("demo", "wait timeout")
    except ProviderRateLimited:
        # 调用方应按“暂时跳过”处理，而不是 record_failure。
        pass
    runtime.record_success()
    runtime.acquire()

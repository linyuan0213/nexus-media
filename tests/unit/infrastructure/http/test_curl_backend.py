"""curl_cffi backend 选择与 TLS 回退测试."""

from types import SimpleNamespace

import httpx2

from app.infrastructure.http.backends.base import is_tls_transport_error
from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig


def test_tls_error_classifier():
    assert is_tls_transport_error(
        RuntimeError("[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol")
    )
    assert is_tls_transport_error(RuntimeError("TLS handshake failed"))
    assert not is_tls_transport_error(RuntimeError("HTTP 403 Forbidden"))
    assert not is_tls_transport_error(RuntimeError("rate limit"))


def test_auto_backend_falls_back_after_tls_error():
    client = HttpClient(config=HttpClientConfig(backend="auto", timeout=1))
    client._retry = lambda fn: fn()  # type: ignore[method-assign]
    client._client = SimpleNamespace(
        request=lambda *args, **kwargs: (_ for _ in ()).throw(httpx2.ConnectError("SSL: UNEXPECTED_EOF_WHILE_READING"))
    )
    expected = httpx2.Response(
        200,
        content=b"ok",
        request=httpx2.Request("GET", "https://example.com"),
    )
    client._curl_client = SimpleNamespace(request=lambda *args, **kwargs: expected)  # type: ignore[assignment]
    try:
        response = client.get("https://example.com")
        assert response.text == "ok"
    finally:
        client.close()


def test_profile_fallback_chain():
    from app.infrastructure.http.backends.curl_cffi_backend import _can_retry_profile, _profiles

    profiles = _profiles("chrome142")
    assert profiles[0] == "chrome142"
    assert "chrome124" in profiles
    assert None in profiles
    assert _can_retry_profile(RuntimeError("OPENSSL_internal:invalid library"))
    assert not _can_retry_profile(RuntimeError("HTTP 403"))

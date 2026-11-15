"""HTTP backend 协议与 TLS 错误分类."""

from __future__ import annotations

from typing import Any, Protocol

import httpx2


class HttpBackend(Protocol):
    def request(self, method: str, url: str, **kwargs: Any) -> httpx2.Response: ...

    def close(self) -> None: ...


def is_tls_transport_error(exc: BaseException) -> bool:
    """只把 TLS 握手/连接重置视为可切换 curl_cffi 的传输错误."""
    text = str(exc or "").lower()
    return any(
        marker in text
        for marker in (
            "unexpected eof",
            "unexpected_eof",
            "ssl",
            "tls",
            "handshake",
            "connection reset",
            "connection_reset",
            "eof occurred in violation of protocol",
        )
    )

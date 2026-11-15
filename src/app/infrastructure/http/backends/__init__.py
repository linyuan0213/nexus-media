"""HTTP backend 实现（httpx2 / curl_cffi）."""

from app.infrastructure.http.backends.base import HttpBackend, is_tls_transport_error
from app.infrastructure.http.backends.curl_cffi_backend import AsyncCurlCffiBackend, CurlCffiBackend

__all__ = ["AsyncCurlCffiBackend", "CurlCffiBackend", "HttpBackend", "is_tls_transport_error"]

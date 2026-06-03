"""HTTP 客户端基础设施 — 基于 httpx 的统一同步/异步 HTTP 客户端."""

from app.infrastructure.http.async_client import AsyncHttpClient
from app.infrastructure.http.auth import (
    ApiKeyAuth,
    BearerAuth,
    CookieAuth,
)
from app.infrastructure.http.cache import HttpCacheConfig
from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.infrastructure.http.exceptions import (
    HttpAuthError,
    HttpClientError,
    HttpConnectionError,
    HttpTimeoutError,
)
from app.infrastructure.http.retry import HttpRetryConfig

__all__ = [
    "ApiKeyAuth",
    "AsyncHttpClient",
    "BearerAuth",
    "CookieAuth",
    "HttpAuthError",
    "HttpCacheConfig",
    "HttpClient",
    "HttpClientConfig",
    "HttpClientError",
    "HttpConnectionError",
    "HttpRetryConfig",
    "HttpTimeoutError",
]

"""同步 HTTP 客户端 Facade."""

from typing import Any

import httpx

from app.infrastructure.http.cache import HttpCacheConfig
from app.infrastructure.http.config import HttpClientConfig
from app.infrastructure.http.exceptions import HttpClientError
from app.infrastructure.http.middleware import HttpMiddleware
from app.infrastructure.http.retry import HttpRetryConfig
from app.infrastructure.rate_limiter import RateLimitEngine


class HttpClient:
    """同步 HTTP 客户端 Facade.

    封装 httpx.Client，内置 tenacity 重试、RateLimitEngine 限流、HttpCacheConfig 缓存。
    所有同步 HTTP 调用（站点签到、下载器 API、媒体服务器）使用此类。
    """

    def __init__(
        self,
        config: HttpClientConfig | None = None,
        retry_config: HttpRetryConfig | None = None,
        rate_limiter: RateLimitEngine | None = None,
        cache: HttpCacheConfig | None = None,
        middlewares: list[HttpMiddleware] | None = None,
    ):
        self._config = config or HttpClientConfig()
        self._retry = (retry_config or HttpRetryConfig()).build_retrying()
        self._rate_limiter = rate_limiter
        self._cache = cache
        self._middlewares = middlewares or []
        self._client = self._build_client()

    def _build_client(self) -> httpx.Client:
        limits = httpx.Limits(
            max_connections=self._config.max_connections,
            max_keepalive_connections=self._config.max_keepalive,
        )
        transport = httpx.HTTPTransport(limits=limits, retries=0)
        timeout = httpx.Timeout(
            self._config.timeout,
            connect=self._config.connect_timeout,
        )
        return httpx.Client(
            transport=transport,
            timeout=timeout,
            follow_redirects=self._config.follow_redirects,
            verify=self._config.verify_ssl,
            proxy=self._config.proxy_url,
            auth=self._config.auth,
            headers=self._config.default_headers,
        )

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """执行 HTTP 请求，tenacity 自动重试 + 异常转换."""
        rate_limit_key = kwargs.pop("rate_limit_key", None)
        rate_limit_rate = kwargs.pop("rate_limit_rate", None)
        raise_on_error = kwargs.pop("raise_for_status", True)
        cache_ttl = kwargs.pop("cache_ttl", None)
        cache_bypass = kwargs.pop("cache_bypass", False)

        if self._rate_limiter and rate_limit_key and rate_limit_rate:
            acquired = self._rate_limiter.acquire(
                key=rate_limit_key,
                rate=rate_limit_rate,
                timeout=None,
            )
            if not acquired:
                raise HttpClientError(f"Rate limit exceeded: {rate_limit_key}")

        if self._cache and not cache_bypass:
            cache_key = self._build_cache_key(method, url, kwargs)
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        def _do_request() -> httpx.Response:
            response = self._client.request(method, url, **kwargs)
            if raise_on_error:
                response.raise_for_status()
            return response

        # 请求中间件链路
        if self._middlewares:
            tmp_request = httpx.Request(
                method, url, **{k: v for k, v in kwargs.items() if k in ("headers", "params", "cookies")}
            )
            for mw in self._middlewares:
                tmp_request = mw.process_request(tmp_request)

        try:
            result = self._retry(_do_request)
        except httpx.HTTPError as e:
            raise HttpClientError.from_httpx(e) from e

        # 响应中间件链路
        for mw in self._middlewares:
            result = mw.process_response(result)

        if self._cache and not cache_bypass:
            if self._cache.is_cacheable(method, result):
                ttl = cache_ttl if cache_ttl is not None else self._cache.default_ttl
                cache_key = self._build_cache_key(method, url, kwargs)
                self._cache.set(cache_key, result, ttl=ttl)

        return result

    @staticmethod
    def _build_cache_key(method: str, url: str, kwargs: dict) -> str:
        params = kwargs.get("params")
        if params:
            if isinstance(params, dict):
                sorted_params = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
            else:
                sorted_params = str(params)
            return f"http:{method}:{url}?{sorted_params}"
        return f"http:{method}:{url}"

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("DELETE", url, **kwargs)

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

"""异步 HTTP 客户端 Facade."""

from typing import Any

import httpx

from app.infrastructure.http.cache import HttpCacheConfig
from app.infrastructure.http.config import HttpClientConfig
from app.infrastructure.http.exceptions import HttpClientError
from app.infrastructure.http.retry import HttpRetryConfig
from app.infrastructure.rate_limiter import RateLimitEngine


class AsyncHttpClient:
    """异步 HTTP 客户端 Facade.

    封装 httpx.AsyncClient，支持 HTTP/2，内置 tenacity 异步重试、RateLimitEngine 限流、HttpCacheConfig 缓存。
    用于高并发场景：并发站点搜索、RSS 订阅轮询、批量媒体元数据获取。
    """

    def __init__(
        self,
        config: HttpClientConfig | None = None,
        retry_config: HttpRetryConfig | None = None,
        rate_limiter: RateLimitEngine | None = None,
        cache: HttpCacheConfig | None = None,
    ):
        self._config = config or HttpClientConfig()
        self._retry = (retry_config or HttpRetryConfig()).build_async_retrying()
        self._rate_limiter = rate_limiter
        self._cache = cache
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """延迟初始化 AsyncClient."""
        if self._client is None:
            limits = httpx.Limits(
                max_connections=self._config.max_connections,
                max_keepalive_connections=self._config.max_keepalive,
            )
            transport = httpx.AsyncHTTPTransport(limits=limits, retries=0)
            self._client = httpx.AsyncClient(
                transport=transport,
                timeout=self._config.timeout,
                follow_redirects=self._config.follow_redirects,
                verify=self._config.verify_ssl,
                http2=self._config.enable_http2,
                proxy=self._config.proxy_url,
                auth=self._config.auth,
            )
        return self._client

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """执行异步 HTTP 请求，tenacity 自动重试 + 异常转换."""
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

        client = await self._get_client()

        async def _do_request() -> httpx.Response:
            response = await client.request(method, url, **kwargs)
            if raise_on_error:
                response.raise_for_status()
            return response

        try:
            result = await self._retry(_do_request)
        except httpx.HTTPError as e:
            raise HttpClientError.from_httpx(e) from e

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

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("DELETE", url, **kwargs)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

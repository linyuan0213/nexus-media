# ADR-010: HTTP 客户端统一重构 — 以 httpx 替换 requests

## Status

Proposed

## Date

2026-06-02

## Context

当前项目使用 `requests` 作为 HTTP 客户端，分布在 20+ 个文件中。随着异步需求增长（事件系统、WebSocket、并发站点签到），`requests` 的同步阻塞特性成为瓶颈。

### requests 使用现状

| 使用模式 | 文件数 | 典型场景 |
|----------|--------|----------|
| `requests.get/post` | 8 | 简单 API 调用（消息推送、站点信息） |
| `requests.Session()` | 12 | 会话保持（站点 Cookie、下载器 API） |
| `requests.request()` | 3 | 通用请求（代理、Webhook） |
| `HTTPAdapter` | 2 | 连接池配置（图片代理） |
| `requests.exceptions` | 2 | 异常处理（刮削图片下载） |

### requests 的固有问题

1. **同步阻塞**：所有请求阻塞当前线程，高并发场景需要大量线程
2. **无原生异步**：`asyncio` 生态中需要 `aiohttp` 或 `run_in_executor` 包装
3. **HTTP/2 不支持**：现代站点和 API 普遍支持 HTTP/2，requests 无法利用
4. **API 不一致**：同步/异步两套代码（requests vs aiohttp），维护成本高

---

## 目标

- 统一同步/异步 HTTP 客户端为 `httpx`
- 支持 HTTP/2，提升站点访问性能
- 内置重试、限流、代理、日志等横切关注点
- 与现有 DI 容器集成，可测试、可 Mock
- 消除所有 `import requests`

---

## 方案设计

### 架构图

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          HTTP Client Layer                                │
├──────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐       │
│  │  HttpClient  │  │  tenacity    │  │  RateLimitEngine         │       │
│  │  (Facade)    │  │  (重试)       │  │  (复用已有基础设施)       │       │
│  └──────┬───────┘  └──────┬───────┘  └────────────┬─────────────┘       │
│         │                 │                       │                      │
│         └─────────────────┴───────────┬───────────┘                      │
│                              ┌────────┴────────┐                        │
│                              │  HttpCache      │  ← 缓存层（新增）        │
│                              │  (CacheAdapter) │                        │
│                              └────────┬────────┘                        │
│                                       │                                  │
│                         ┌─────────────┴──────────────┐                  │
│                         │       TransportLayer        │                  │
│                         │  ┌──────────────────┐       │                  │
│                         │  │  httpx.Client    │  同步  │                  │
│                         │  │    (HTTP/1.1)    │       │                  │
│                         │  └──────────────────┘       │                  │
│                         │  ┌──────────────────┐       │                  │
│                         │  │ httpx.AsyncClient│  异步  │                  │
│                         │  │    (HTTP/2)      │       │                  │
│                         │  └──────────────────┘       │                  │
│                         └─────────────────────────────┘                  │
└──────────────────────────────────────────────────────────────────────────┘
```

### 目录结构

```
src/app/infrastructure/http/
├── __init__.py              # export HttpClient, AsyncHttpClient
├── client.py                # HttpClient Facade
├── async_client.py          # AsyncHttpClient Facade
├── config.py                # HttpClientConfig dataclass
├── exceptions.py            # 统一异常体系
├── retry.py                 # HttpRetryConfig（基于 tenacity）
├── auth.py                  # CookieAuth, BearerAuth, ApiKeyAuth
├── cache.py                 # HttpCacheConfig + HttpCacheMiddleware
└── middleware.py            # 请求/响应中间件链
```

### 核心设计决策

#### 1. 双客户端设计：同步 + 异步

```python
# app/infrastructure/http/client.py
import httpx
from typing import Any

from app.infrastructure.http.config import HttpClientConfig
from app.infrastructure.http.exceptions import HttpClientError
from app.infrastructure.http.retry import HttpRetryConfig


class HttpClient:
    """同步 HTTP 客户端 Facade.

    封装 httpx.Client，内置 tenacity 重试，支持 RateLimitEngine 限流注入。
    所有同步 HTTP 调用（站点签到、下载器 API、媒体服务器）使用此类。
    """

    def __init__(
        self,
        config: HttpClientConfig | None = None,
        retry_config: HttpRetryConfig | None = None,
        rate_limiter: "RateLimitEngine | None" = None,
        cache: "HttpCacheConfig | None" = None,
    ):
        self._config = config or HttpClientConfig()
        self._retry = (retry_config or HttpRetryConfig()).build_retrying()
        self._rate_limiter = rate_limiter
        self._cache = cache
        self._client = self._build_client()

    def _build_client(self) -> httpx.Client:
        limits = httpx.Limits(
            max_connections=self._config.max_connections,
            max_keepalive_connections=self._config.max_keepalive,
        )
        transport = httpx.HTTPTransport(limits=limits, retries=0)
        return httpx.Client(
            transport=transport,
            timeout=self._config.timeout,
            follow_redirects=self._config.follow_redirects,
            verify=self._config.verify_ssl,
            proxy=self._config.proxy_url,
            auth=self._config.auth,
        )

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """执行 HTTP 请求，tenacity 自动重试 + 异常转换.

        :param raise_for_status: 是否自动抛异常（默认 True），
            设为 False 可手动检查 response.status_code
        """
        raise_on_error = kwargs.pop("raise_for_status", True)

        def _do_request() -> httpx.Response:
            response = self._client.request(method, url, **kwargs)
            if raise_on_error:
                response.raise_for_status()
            return response

        try:
            return self._retry(_do_request)
        except httpx.HTTPError as e:
            raise HttpClientError.from_httpx(e) from e

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
```

```python
# app/infrastructure/http/async_client.py
import httpx
from typing import Any

from app.infrastructure.http.config import HttpClientConfig
from app.infrastructure.http.exceptions import HttpClientError
from app.infrastructure.http.retry import HttpRetryConfig


class AsyncHttpClient:
    """异步 HTTP 客户端 Facade.

    封装 httpx.AsyncClient，支持 HTTP/2，tenacity 异步重试，支持 RateLimitEngine 限流注入。
    用于高并发场景：并发站点搜索、RSS 订阅轮询、批量媒体元数据获取。
    """

    def __init__(
        self,
        config: HttpClientConfig | None = None,
        retry_config: HttpRetryConfig | None = None,
        rate_limiter: "RateLimitEngine | None" = None,
        cache: "HttpCacheConfig | None" = None,
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
        """执行异步 HTTP 请求，tenacity 自动重试 + 异常转换.

        :param raise_for_status: 是否自动抛异常（默认 True），
            设为 False 可手动检查 response.status_code
        """
        raise_on_error = kwargs.pop("raise_for_status", True)
        client = await self._get_client()

        async def _do_request() -> httpx.Response:
            response = await client.request(method, url, **kwargs)
            if raise_on_error:
                response.raise_for_status()
            return response

        try:
            return await self._retry(_do_request)
        except httpx.HTTPError as e:
            raise HttpClientError.from_httpx(e) from e

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
```

#### 2. 统一异常体系

```python
# app/infrastructure/http/exceptions.py
import httpx


class HttpClientError(Exception):
    """HTTP 客户端统一异常基类."""

    def __init__(self, message: str, status_code: int | None = None, response_text: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text

    @classmethod
    def from_httpx(cls, exc: httpx.HTTPError) -> "HttpClientError":
        """从 httpx 异常转换."""
        status_code = None
        response_text = None
        if isinstance(exc, httpx.HTTPStatusError):
            status_code = exc.response.status_code
            try:
                response_text = exc.response.text[:500]
            except Exception:
                pass
        return cls(
            message=str(exc),
            status_code=status_code,
            response_text=response_text,
        )


class HttpTimeoutError(HttpClientError):
    """请求超时."""


class HttpConnectionError(HttpClientError):
    """连接失败."""


class HttpAuthError(HttpClientError):
    """认证失败（401/403）."""
```

#### 3. 基于 tenacity 的重试策略

项目已依赖 `tenacity>=9.1.4`，不重复造轮子。`HttpClient` 使用 `tenacity.Retrying` 上下文，`AsyncHttpClient` 使用 `tenacity.AsyncRetrying`。

```python
# app/infrastructure/http/retry.py
from dataclasses import dataclass
from typing import Any

from tenacity import (
    AsyncRetrying,
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

import httpx


@dataclass
class HttpRetryConfig:
    """HTTP 重试配置."""

    max_attempts: int = 3
    min_wait: float = 1.0
    max_wait: float = 60.0
    exp_base: float = 2.0

    def build_retrying(self, **kwargs: Any) -> Retrying:
        """构建 tenacity.Retrying（同步）."""
        return Retrying(
            stop=stop_after_attempt(self.max_attempts),
            wait=wait_exponential(multiplier=self.min_wait, exp_base=self.exp_base, max=self.max_wait),
            retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
            reraise=True,
            **kwargs,
        )

    def build_async_retrying(self, **kwargs: Any) -> AsyncRetrying:
        """构建 tenacity.AsyncRetrying（异步）."""
        return AsyncRetrying(
            stop=stop_after_attempt(self.max_attempts),
            wait=wait_exponential(multiplier=self.min_wait, exp_base=self.exp_base, max=self.max_wait),
            retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
            reraise=True,
            **kwargs,
        )
```

#### 4. 限流器集成（RateLimitEngine）

项目已存在独立的限流基础设施 `app.infrastructure.rate_limiter`，提供 `RateLimitEngine`、`MemoryTokenBucketBackend`、`RedisTokenBucketBackend` 等实现。

**HttpClient 与 RateLimitEngine 的集成方式**：通过构造函数注入，在 `request()` 层对指定 key 进行速率控制。

```python
# app/infrastructure/http/client.py（限流集成示例）

class HttpClient:
    def __init__(
        self,
        config: HttpClientConfig | None = None,
        retry_config: HttpRetryConfig | None = None,
        rate_limiter: "RateLimitEngine | None" = None,
    ):
        self._config = config or HttpClientConfig()
        self._retry = (retry_config or HttpRetryConfig()).build_retrying()
        self._rate_limiter = rate_limiter
        self._client = self._build_client()

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        rate_limit_key = kwargs.pop("rate_limit_key", None)
        rate_limit_rate = kwargs.pop("rate_limit_rate", None)
        if self._rate_limiter and rate_limit_key and rate_limit_rate:
            acquired = self._rate_limiter.acquire(
                key=rate_limit_key,
                rate=rate_limit_rate,
                timeout=None,  # 非阻塞，超限直接失败由 tenacity 重试兜底
            )
            if not acquired:
                raise HttpClientError(f"Rate limit exceeded: {rate_limit_key}")

        def _do_request() -> httpx.Response:
            response = self._client.request(method, url, **kwargs)
            response.raise_for_status()
            return response

        try:
            return self._retry(_do_request)
        except httpx.HTTPError as e:
            raise HttpClientError.from_httpx(e) from e
```

**限流器使用示例**：

```python
from app.infrastructure.http import HttpClient
from app.infrastructure.rate_limiter import RateLimitEngine, MemoryTokenBucketBackend

# 注入限流器
engine = RateLimitEngine(backend=MemoryTokenBucketBackend())
client = HttpClient(rate_limiter=engine)

# 按站点维度限流
resp = client.get(
    url,
    rate_limit_key=f"site:{site_id}",
    rate_limit_rate="10/m",  # 每分钟 10 次
)
```

`AsyncHttpClient` 的限流集成方式与同步版本一致，异步场景下 `RateLimitEngine` 的内存后端已具备线程安全（`threading.RLock`），Redis 后端天然支持分布式并发。

#### 5. 认证模块

```python
# app/infrastructure/http/auth.py
from typing import Any

import httpx


class CookieAuth(httpx.Auth):
    """Cookie 认证（兼容 httpx.Auth）."""

    def __init__(self, cookies: dict[str, str] | str | None = None):
        self._cookies = self._parse_cookies(cookies)

    @staticmethod
    def _parse_cookies(cookies: dict[str, str] | str | None) -> dict[str, str]:
        if cookies is None:
            return {}
        if isinstance(cookies, dict):
            return cookies
        result = {}
        for part in str(cookies).split(";"):
            part = part.strip()
            if "=" in part:
                key, value = part.split("=", 1)
                result[key.strip()] = value.strip()
        return result

    def auth_flow(self, request: httpx.Request) -> Any:
        if self._cookies:
            cookie_str = "; ".join(f"{k}={v}" for k, v in self._cookies.items())
            request.headers["Cookie"] = cookie_str
        yield request

    def apply(self, request: httpx.Request) -> httpx.Request:
        """直接修改 request（兼容旧用法）."""
        if self._cookies:
            cookie_str = "; ".join(f"{k}={v}" for k, v in self._cookies.items())
            request.headers["Cookie"] = cookie_str
        return request


class BearerAuth(httpx.Auth):
    """Bearer Token 认证."""

    def __init__(self, token: str):
        self._token = token

    def auth_flow(self, request: httpx.Request) -> Any:
        request.headers["Authorization"] = f"Bearer {self._token}"
        yield request


class ApiKeyAuth(httpx.Auth):
    """API Key 认证（支持 header 或 query 参数）."""

    def __init__(self, key: str, value: str, location: str = "header"):
        self._key = key
        self._value = value
        self._location = location

    def auth_flow(self, request: httpx.Request) -> Any:
        if self._location == "header":
            request.headers[self._key] = self._value
        elif self._location == "query":
            request.url = request.url.copy_merge_params({self._key: self._value})
        yield request
```

#### 6. 配置模型

```python
# app/infrastructure/http/config.py
from dataclasses import dataclass, field

import httpx


@dataclass
class HttpClientConfig:
    """HTTP 客户端配置."""

    # 连接池
    max_connections: int = 100
    max_keepalive: int = 20

    # 超时
    timeout: float = 30.0
    connect_timeout: float = 10.0

    # 行为
    follow_redirects: bool = True
    verify_ssl: bool = True
    enable_http2: bool = True  # AsyncHttpClient 默认启用

    # 代理
    proxy_url: str | None = None

    # 默认请求头
    default_headers: dict[str, str] | None = None

    # 认证（httpx.Auth 子类）
    auth: httpx.Auth | None = field(default=None, repr=False)
```

#### 7. DI 容器集成（可选）

`HttpClient` 支持直接实例化，**不强制依赖 DI**。DI 容器仅注册一个默认单例，供需要统一管理生命周期的场景使用。

```python
# 直接实例化（推荐简单场景）
from app.infrastructure.http import HttpClient, HttpClientConfig

client = HttpClient(config=HttpClientConfig(timeout=60.0))

# 通过 DI 获取（推荐需要统一管理连接池的场景）
from app.di import container
client = container.http_client()
```

```python
# app/di/container.py (可选注册)
class Container(containers.DeclarativeContainer):
    http_client: Provider["HttpClient"] = providers.Singleton(HttpClient)
    async_http_client: Provider["AsyncHttpClient"] = providers.Singleton(AsyncHttpClient)
```

#### 8. 中间件扩展点

```python
# app/infrastructure/http/middleware.py
from abc import ABC, abstractmethod
from typing import Any

import httpx


class HttpMiddleware(ABC):
    """HTTP 请求/响应中间件基类."""

    @abstractmethod
    def process_request(self, request: httpx.Request) -> httpx.Request:
        """处理请求（添加 header、签名等）."""

    @abstractmethod
    def process_response(self, response: httpx.Response) -> httpx.Response:
        """处理响应（日志、指标等）."""


class LoggingMiddleware(HttpMiddleware):
    """请求日志中间件."""

    def process_request(self, request: httpx.Request) -> httpx.Request:
        log.debug(f"[HTTP] {request.method} {request.url}")
        return request

    def process_response(self, response: httpx.Response) -> httpx.Response:
        log.debug(f"[HTTP] {response.status_code} {response.request.url}")
        return response
```

#### 9. __init__.py 导出说明

```python
# app/infrastructure/http/__init__.py
from app.infrastructure.http.async_client import AsyncHttpClient
from app.infrastructure.http.auth import ApiKeyAuth, BearerAuth, CookieAuth
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
```

#### 10. HTTP 响应缓存（HttpCacheConfig）

复用项目已有的缓存基础设施 `app.infrastructure.cache_system`（`CacheAdapter` → `MemoryCacheAdapter` / `RedisCacheAdapter` / `TieredCacheAdapter`），在 `HttpClient` 内部实现一层透明 HTTP 缓存，专用于 GET 请求的高频调用场景（TMDB API、豆瓣 API、Bangumi 元数据等）。

**缓存键设计**：

```
cache_key = f"http:{method}:{url}:{sorted_query_params}"
```

GET 请求默认缓存，POST/PUT/DELETE 不缓存。可通过 `cache_methods` 配置扩展。

**配置模型**：

```python
# app/infrastructure/http/cache.py
from dataclasses import dataclass, field
from typing import Any

from app.infrastructure.cache_system import CacheAdapter


@dataclass
class HttpCacheConfig:
    """HTTP 客户端缓存配置.

    注入 CacheAdapter 实例（可通过 CacheManager.get_or_create() 获取），
    HttpClient 在 request() 层自动进行缓存读写。
    """

    cache_adapter: CacheAdapter | None = None
    default_ttl: int = 300  # 默认缓存 5 分钟
    cache_methods: tuple[str, ...] = ("GET",)

    # 最大缓存 value 大小（字节），超过不缓存
    max_value_size: int = 10 * 1024 * 1024  # 10MB
```

**HttpClient 集成**：

```python
# app/infrastructure/http/client.py（缓存集成示例）

class HttpClient:
    def __init__(
        self,
        config: HttpClientConfig | None = None,
        retry_config: HttpRetryConfig | None = None,
        rate_limiter: "RateLimitEngine | None" = None,
        cache: HttpCacheConfig | None = None,
    ):
        ...
        self._cache = cache

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        cache_ttl = kwargs.pop("cache_ttl", None)
        cache_bypass = kwargs.pop("cache_bypass", False)

        # 尝试从缓存读取
        if self._cache and not cache_bypass:
            cache_key = self._build_cache_key(method, url, kwargs)
            cached = self._cache.cache_adapter.get(cache_key)
            if cached is not None:
                return cached

        # 执行请求
        response = super().request(method, url, **kwargs)

        # 写入缓存
        if self._cache and self._can_cache(method, response):
            cache_key = self._build_cache_key(method, url, kwargs)
            ttl = cache_ttl if cache_ttl is not None else self._cache.default_ttl
            self._cache.cache_adapter.set(cache_key, response, ttl=ttl)

        return response

    def _can_cache(self, method: str, response: httpx.Response) -> bool:
        return (
            method in self._cache.cache_methods
            and response.status_code == 200
            and len(response.content) <= self._cache.max_value_size
        )

    @staticmethod
    def _build_cache_key(method: str, url: str, kwargs: dict) -> str:
        params = kwargs.get("params")
        if params:
            sorted_params = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
            return f"http:{method}:{url}?{sorted_params}"
        return f"http:{method}:{url}"
```

**使用示例**：

```python
from app.infrastructure.cache_system import get_cache_manager
from app.infrastructure.http import HttpClient, HttpClientConfig, HttpCacheConfig

# 创建缓存适配器（内存 + Redis 二级缓存）
adapter = get_cache_manager().get_or_create("http", cache_type="tiered", memory_maxsize=500)

# 注入缓存
client = HttpClient(
    config=HttpClientConfig(timeout=30),
    cache=HttpCacheConfig(cache_adapter=adapter, default_ttl=3600),
)

# 首次调用 → 请求 TMDB，写入缓存
resp = client.get("https://api.themoviedb.org/3/movie/550", params={"api_key": "..."})

# 后续调用 → 缓存命中（1 小时内不再发起 HTTP 请求）
resp = client.get("https://api.themoviedb.org/3/movie/550", params={"api_key": "..."})

# 强制刷新
resp = client.get("https://api.themoviedb.org/3/movie/550", params={"api_key": "..."}, cache_bypass=True)

# 自定义 TTL（30 分钟）
resp = client.get("https://api.themoviedb.org/3/movie/550", params={"api_key": "..."}, cache_ttl=1800)
```

**与 cache_system 的集成关系**：

```
                   ┌──────────────────────────┐
                   │       HttpClient          │
                   │  ┌───────────────────┐    │
                   │  │  request()        │    │
                   │  │  cache lookup ────────►│  CacheAdapter
                   │  │  cache store ◄────────│  (Memory / Redis / Tiered)
                   │  │  actual request ──────►│  httpx.Client
                   │  └───────────────────┘    │
                   └──────────────────────────┘
```

`AsyncHttpClient` 的缓存集成方式与同步版本一致——`CacheAdapter` 本身不关心同步/异步，`HttpCacheConfig` 可在两个客户端间共享。

**不缓存的情况**：
- `method` 不在 `cache_methods` 中（默认只缓存 GET）
- `response.status_code != 200`
- 响应体超过 `max_value_size`
- 调用时传了 `cache_bypass=True`


---

## 实施计划

### Phase 1：基础设施搭建

1. 新建 `app/infrastructure/http/` 包
2. 实现 `HttpClient`、`AsyncHttpClient`、`HttpRetryConfig`、`HttpClientConfig`
3. 实现 `HttpCacheConfig`（基于 `cache_system.CacheAdapter` 的 HTTP 响应缓存）
4. DI 容器注册 provider
5. 添加单元测试（mock httpx 传输层）

### Phase 2：核心模块迁移

按优先级逐个替换 `import requests`：

| 优先级 | 模块 | 原因 |
|--------|------|------|
| P0 | `app/utils/http_utils.py`（`RequestUtils`） | 被大量模块依赖的核心工具，255+ 处调用 |
| P0 | `app/sites/site_userinfo.py` | 站点信息获取，高频调用 |
| P1 | `app/indexer/client/jackett.py` | 搜索索引器 |
| P1 | `app/mediaserver/client/fnos_api.py` | 媒体服务器 API |
| P2 | `app/message/client/*` | 消息推送（低并发） |
| P2 | `app/storage/backends/*` | 存储后端 |
| P3 | 插件 | 独立生命周期，可延后 |

### Phase 3：内嵌 API 客户端重构

`app/infrastructure/external/` 下的 `tmdbv3api`、`doubanapi` 是项目内嵌的 API 客户端（非第三方库），需要同步重构为 httpx：

| 模块 | 当前实现 | 改造后 |
|------|----------|--------|
| `tmdbv3api/tmdb.py` | `requests.Session()` | `httpx.Client()` |
| `doubanapi/apiv2.py` | `requests.Session()` | `httpx.Client()` |
| `doubanapi/webapi.py` | `requests.Session()` | `httpx.Client()` |

改造方式：
- 注入 `HttpClient` 替代自建 `requests.Session`
- 复用 `HttpRetryConfig`（tenacity 重试）替代自建重试逻辑
- 统一异常转换：`requests.exceptions.*` → `HttpClientError`

### Phase 4：TMDB 缓存集成

为高频元数据查询启用 `HttpCacheConfig`：

| 缓存 key | 场景 | 推荐 TTL |
|----------|------|----------|
| `tmdb:movie:{id}` | 电影详情 | 24h |
| `tmdb:tv:{id}` | 剧集详情 | 24h |
| `tmdb:person:{id}` | 人员信息 | 30d |
| `tmdb:search:{query}` | 搜索结果 | 1h |
| `douban:movie:{id}` | 豆瓣电影 | 24h |
| `bangumi:{id}` | Bangumi 条目 | 1h |

使用 `CacheManager` 创建命名缓存 `http_tmdb`（Redis + 内存二级缓存），在 `tmdb_client.py` 初始化的 `HttpClient` 中注入。

### Phase 5：清理与验证

1. 全局搜索 `import requests`，确保清零
2. 性能基准测试（httpx HTTP/2 vs requests HTTP/1.1）
3. 异常场景测试（超时、重试、连接失败）

---

## 使用示例

### 同步调用（站点签到）

```python
# 改造前（无 async 支持，只能用线程池）
from concurrent.futures import ThreadPoolExecutor
with ThreadPoolExecutor(max_workers=10) as pool:
    results = pool.map(fetch_site, sites)

# 改造后（原生 async + HTTP/2）
import asyncio
from app.infrastructure.http import AsyncHttpClient

async def search_all(sites):
    client = AsyncHttpClient()
    tasks = [client.get(site.url) for site in sites]
    return await asyncio.gather(*tasks, return_exceptions=True)
```

### RequestUtils 迁移示例

```python
# 改造前
from app.utils import RequestUtils

res = RequestUtils(
    headers=headers,
    cookies=cookie,
    proxies=proxies,
    timeout=30,
).get_res(url)

# 改造后
from app.infrastructure.http import HttpClient

client = HttpClient()
res = client.get(
    url,
    headers=headers,
    cookies=cookie,
    proxy=proxies,
)
```

### 带重试的配置

```python
from app.infrastructure.http import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.infrastructure.http.retry import HttpRetryConfig

client = HttpClient(
    config=HttpClientConfig(timeout=60.0),
    retry_config=HttpRetryConfig(max_attempts=5, min_wait=2.0),
)
```

---

## Consequences

### 正面影响

- **性能提升**：HTTP/2 多路复用减少连接开销，异步支持提升并发能力
- **API 统一**：同步/异步一套接口，学习成本低
- **可测试性**：httpx 原生支持 Mock Transport，单元测试更简单
- **现代化**：httpx 是 FastAPI/Starlette 生态的标准选择

### 负面影响

- **迁移成本**：20+ 文件需要修改，`RequestUtils` 255+ 处调用需逐一切换
- **HTTP/2 兼容性**：部分老旧站点可能不支持 HTTP/2，需降级处理
- **异常处理变更**：`requests.exceptions.*` → `httpx.*`，调用方需同步修改

### 检查清单

```bash
# 1. 确认 requests 已清零
grep -r "import requests\|from requests" src/ --include="*.py"

# 2. 确认 RequestUtils 已清零
grep -r "RequestUtils" src/ --include="*.py"

# 3. 确认 httpx 已引入
grep -r "import httpx\|from httpx" src/ --include="*.py"

# 4. 运行测试
uv run pytest tests/ -q
```

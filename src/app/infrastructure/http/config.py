"""HTTP 客户端配置."""

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

"""HTTP 客户端配置."""

from dataclasses import dataclass, field
from typing import Literal

import httpx2

from app.domain.browser_mode import BrowserModeConfig


@dataclass
class HttpClientConfig:
    """HTTP 客户端配置."""

    # 连接池
    max_connections: int = 100
    max_keepalive: int = 20

    # 超时
    timeout: float = 120.0
    connect_timeout: float = 10.0

    # 行为
    follow_redirects: bool = True
    verify_ssl: bool = True
    enable_http2: bool = True  # AsyncHttpClient 默认启用

    # 代理
    proxy_url: str | None = None

    # 传输后端：auto 先 httpx，TLS 指纹失败后切 curl_cffi；curl_cffi 直接使用浏览器指纹
    backend: Literal["auto", "httpx", "curl_cffi"] = "auto"
    impersonate: str | None = None
    backend_retry_on_tls: bool = True
    # curl_cffi 缓冲上限；下载/流式接口应保持 httpx
    max_buffered_size: int = 10 * 1024 * 1024

    # 默认请求头
    default_headers: dict[str, str] | None = None

    # 认证（httpx2.Auth 子类）
    auth: httpx2.Auth | None = field(default=None, repr=False)

    # DNS 映射（主机名 → IP 地址），用于替代 /etc/hosts 修改
    host_mapping: dict[str, str] | None = None

    # 浏览器自动化模式（None 表示不启用）
    browser: BrowserModeConfig | None = None

"""浏览器自动化模式配置（领域值对象）."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BrowserModeConfig:
    """浏览器自动化模式配置."""

    enabled: bool = False
    server_url: str = ""
    session_key: str = "default"
    site_key: str = "default"
    fingerprint_profile: str = "stealth"
    fp_profile_id: str | None = None
    user_agent: str | None = None
    proxy_url: str | None = None
    navigate_timeout: int = 90
    auto_navigate_on_challenge: bool = True
    browser_fetch_on_challenge: bool = True
    render_html: bool = False
    # 持久会话：请求结束后保留浏览器会话（含挑战/2FA 通过后的认证态），供后续复用。
    # 默认 False（用完即删会话，实例由 nexus-chrome 空闲 TTL 保留复用）；
    # 需要长期保持认证态的站点（如 2FA 站点）显式开启。
    persistent_session: bool = False
    # nexus-chrome 认证凭证（API Key / 管理 token），AUTH_PASSWORD 启用时必配
    api_key: str | None = None

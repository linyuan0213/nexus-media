"""浏览器自动化模式工具函数.

提供从站点运行时配置构造 BrowserModeConfig 的能力, 以及渲染 HTML 归一化.
"""

from __future__ import annotations

import hashlib
from urllib.parse import urlsplit

from app.core.settings import settings
from app.domain.browser_mode import BrowserModeConfig


def canonical_site_key(value: str | None) -> str:
    """把站点 URL/域名/ID 统一成浏览器会话键的主域名."""
    text = str(value or "").strip()
    if not text:
        return ""
    if "://" in text:
        parsed = urlsplit(text)
        return f"{parsed.scheme}://{parsed.netloc}".lower()
    return text.lower()


def browser_site_key(site_info: dict | None, fallback: str | None = None) -> str:
    """按站点配置的域名/签到地址生成稳定 session key，避免 name/id/url 分裂会话."""
    info = site_info or {}
    for key in ("domain", "signurl", "rssurl", "strict_url"):
        value = canonical_site_key(info.get(key))
        if value:
            return value
    return canonical_site_key(fallback)


def make_session_key(site_key: str, browser: BrowserModeConfig) -> str:
    """会话隔离键包含站点标识与浏览器配置指纹.

    站点配置由所有用户共享，因此不再加入用户维度；渲染模式只影响请求结果，
    不影响浏览器 Cookie/clearance，不参与 session key。
    """
    identity = "\x1f".join(
        (
            str(site_key or ""),
            str(browser.fingerprint_profile or ""),
            str(browser.fp_profile_id or ""),
            str(browser.user_agent or ""),
            str(browser.proxy_url or ""),
        )
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"{site_key}:{digest}"


def get_chrome_server_url() -> str | None:
    """返回 Chrome 服务器地址，仅在全局启用且已配置时返回。"""
    lab = settings.get("laboratory")
    if not lab.get("chrome_enabled", True):
        return None
    host = lab.get("chrome_server_host")
    return host.rstrip("/") if host else None


def get_default_fp_profile_id() -> str | None:
    """返回系统配置的默认指纹画像 ID（未配置返回 None）。

    所有后台浏览器会话都应使用同一画像，确保 nexus-chrome 侧复用同一个浏览器实例；
    混用 None 与画像 ID 会各自建一个实例，导致实例数膨胀。
    """
    return str((settings.get("laboratory") or {}).get("chrome_fp_profile_id") or "") or None


def get_chrome_api_key() -> str | None:
    """返回 nexus-chrome 访问凭证（复用 laboratory.chrome_admin_token）。

    nexus-chrome 设置 AUTH_PASSWORD 后启用认证：该配置可填管理端创建的
    API Key（ncmk_ 前缀，scope 建议 sessions+profiles），或 FP_ADMIN_TOKEN。
    未配置则不携带凭证（仅适用于 nexus-chrome 本地模式）。
    """
    lab = settings.get("laboratory") or {}
    token = str(lab.get("chrome_admin_token") or "").strip()
    return token or None


def build_browser_mode(
    site_info: dict,
    site_key: str,
    *,
    proxy_url: str | None = None,
    render_html: bool | None = None,
    server_url: str | None = None,
    fp_profile_id: str | None = None,
) -> BrowserModeConfig | None:
    """从站点运行时配置构造浏览器模式配置.

    开关来自 site_info["chrome"], 是用户在站点管理中维护的运行时配置,
    不是静态站点 JSON. fp_profile_id 为该用户的指纹画像（前端采集注入）;
    未显式传入时回退到系统配置的默认指纹（实验室 chrome_fp_profile_id），
    供全局后台流程（站点定时刷新 / RSS 自动化等无用户上下文场景）使用.
    """
    host = server_url
    if not host:
        host = get_chrome_server_url()
    if not host or not site_info.get("chrome"):
        return None

    if not fp_profile_id:
        fp_profile_id = get_default_fp_profile_id()

    browser = BrowserModeConfig(
        enabled=True,
        server_url=host.rstrip("/"),
        session_key=site_key,
        site_key=site_key,
        fingerprint_profile="stealth",
        fp_profile_id=fp_profile_id,
        # 指纹画像自带完整 UA/平台；站点 ua 可能与画像平台不一致（如移动画像配桌面
        # UA），同时下发会造成 UA 与 navigator.platform/WebGL 自相矛盾，被 Cloudflare
        # 判定为异常。仅在无画像时才用站点 ua 覆盖。
        user_agent=None if fp_profile_id else site_info.get("ua"),
        proxy_url=proxy_url,
        render_html=render_html if render_html is not None else bool(site_info.get("browser_render")),
        api_key=get_chrome_api_key(),
        persistent_session=bool(site_info.get("browser_persistent")),
    )
    browser.session_key = make_session_key(site_key, browser)
    return browser

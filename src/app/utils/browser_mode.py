"""浏览器自动化模式工具函数.

提供从站点运行时配置构造 BrowserModeConfig 的能力, 以及渲染 HTML 归一化.
"""

from __future__ import annotations

import hashlib

from lxml import etree

from app.core.settings import settings
from app.infrastructure.http.config import BrowserModeConfig


def make_session_key(site_key: str, browser: BrowserModeConfig) -> str:
    """会话隔离键包含站点标识与浏览器配置指纹.

    配置变化(UA/代理/指纹/渲染模式)会自动换新 session.
    """
    config_hash = hashlib.md5(  # noqa: S303
        f"{browser.fingerprint_profile}:{browser.user_agent}:{browser.proxy_url}:{browser.render_html}".encode()
    ).hexdigest()[:8]
    return f"{site_key}:{config_hash}"


def get_chrome_server_url() -> str | None:
    """返回 Chrome 服务器地址，仅在全局启用且已配置时返回。"""
    lab = settings.get("laboratory")
    if not lab.get("chrome_enabled", True):
        return None
    host = lab.get("chrome_server_host")
    return host.rstrip("/") if host else None


def build_browser_mode(
    site_info: dict,
    site_key: str,
    *,
    proxy_url: str | None = None,
    render_html: bool | None = None,
    server_url: str | None = None,
) -> BrowserModeConfig | None:
    """从站点运行时配置构造浏览器模式配置.

    开关来自 site_info["chrome"], 是用户在站点管理中维护的运行时配置,
    不是静态站点 JSON.
    """
    host = server_url
    if not host:
        host = get_chrome_server_url()
    if not host or not site_info.get("chrome"):
        return None

    browser = BrowserModeConfig(
        enabled=True,
        server_url=host.rstrip("/"),
        session_key=site_key,
        site_key=site_key,
        fingerprint_profile="stealth",
        user_agent=site_info.get("ua"),
        proxy_url=proxy_url,
        render_html=render_html if render_html is not None else bool(site_info.get("browser_render")),
    )
    browser.session_key = make_session_key(site_key, browser)
    return browser


def normalize_rendered_html(html: str) -> str:
    """将浏览器渲染后的 HTML 归一化到与服务端原始 HTML 同构.

    主要处理浏览器自动插入的 <tbody>, 使现有的 `table > tr` 直接子选择器继续命中.
    """
    try:
        doc = etree.HTML(html)
        if doc is None:
            return html
        for tb in doc.xpath("//tbody"):  # type: ignore[union-attr]
            parent = tb.getparent()
            if parent is None:
                continue
            idx = list(parent).index(tb)
            for child in reversed(list(tb)):
                parent.insert(idx, child)
            parent.remove(tb)
        # 保留 body 内容; lxml 的 HTML 方法会输出完整文档, 需提取 body 内部
        body = doc.find("body")
        if body is not None:
            inner = "".join(etree.tostring(child, encoding="unicode") for child in body)
            return inner
        return etree.tostring(doc, encoding="unicode")
    except Exception:
        return html

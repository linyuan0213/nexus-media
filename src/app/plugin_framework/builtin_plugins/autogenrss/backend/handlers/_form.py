"""HTML 站点通用表单 RSS 生成处理器。"""

import re
from typing import cast
from urllib.parse import parse_qs, unquote, urlparse

from lxml import etree

from app.infrastructure.cloudflare import under_challenge
from app.infrastructure.http.auth import CookieAuth
from app.infrastructure.http.exceptions import HttpClientError
from app.plugin_framework.context import PluginContext
from app.sites.utils import is_logged_in

from .base import SiteRssGenContext, SiteRssGenHandler, SiteRssGenResult

DEFAULT_RSS_LINK_SELECTOR = '//a[contains(@href, "linktype=dl")]/@href'


class FormRssGenHandler(SiteRssGenHandler):
    """HTML 站点通用表单 RSS 生成处理器。"""

    site_id = "__form__"

    def __init__(self, plugin_ctx: PluginContext, rate_limiter, site_repo, site_cache, config: dict):
        super().__init__(plugin_ctx, rate_limiter, site_repo, site_cache)
        self._config = config

    def generate(self, ctx: SiteRssGenContext) -> SiteRssGenResult:
        if not ctx.site_url:
            return SiteRssGenResult.success(ctx.site, "")

        site_def = self._plugin_ctx.site_engine.get_by_id(ctx.site_id)
        base_url = self._resolve_base_url(site_def, ctx)
        path = self._config.get("path", "getrss.php").lstrip("/")
        url = f"{base_url}/{path}"
        method = self._config.get("method", "post")
        data = self._config.get("data")
        headers = self._build_headers(ctx)

        if not ctx.cookie and not ctx.headers:
            return SiteRssGenResult.fail(ctx.site, "未配置Cookie或请求头")

        auth = self._resolve_auth(ctx)
        if isinstance(auth, SiteRssGenResult):
            return auth

        self._plugin_ctx.debug(f"{ctx.site} 表单RSS请求: {method.upper()} {url}")
        client = self._http_client(ctx)
        try:
            if method.upper() == "POST":
                res = client.post(url=url, data=data, headers=headers, auth=auth)
            else:
                res = client.get(url=url, params=data, headers=headers, auth=auth)
        except HttpClientError as exc:
            if exc.status_code in (500, 403):
                return SiteRssGenResult.fail(ctx.site, f"状态码：{exc.status_code}")
            return SiteRssGenResult.fail(ctx.site, SiteRssGenResult.SITE_UNREACHABLE)
        except Exception as e:
            self._plugin_ctx.warn(f"{ctx.site} 表单RSS请求异常: {e}")
            return SiteRssGenResult.fail(ctx.site, SiteRssGenResult.SITE_UNREACHABLE)

        text = res.text
        if not is_logged_in(text):
            if under_challenge(text):
                return SiteRssGenResult.fail(ctx.site, SiteRssGenResult.CLOUDFLARE)
            return SiteRssGenResult.fail(ctx.site, SiteRssGenResult.COOKIE_EXPIRED)

        if re.search(r"完成两步验证", text, re.IGNORECASE):
            return SiteRssGenResult.fail(ctx.site, SiteRssGenResult.NEED_2FA)

        rss_link = self._parse_rss_link(text)
        self._plugin_ctx.debug(f"生成的rss: {rss_link}")
        if rss_link:
            self._save_rss_url(ctx.raw.get("id"), rss_link)
            return SiteRssGenResult.success(ctx.site)
        return SiteRssGenResult.fail(ctx.site, "未解析到RSS链接")

    def _resolve_auth(self, ctx: SiteRssGenContext):
        if ctx.cookie:
            return CookieAuth(CookieAuth._parse_cookies(ctx.cookie))
        return None

    def _parse_rss_link(self, html_text: str) -> str:
        if not html_text:
            return ""
        selector = self._config.get("rss_link_selector") or DEFAULT_RSS_LINK_SELECTOR
        html = etree.HTML(html_text)
        if html is None:
            return ""
        href = next(
            (h for h in cast(list, html.xpath(selector)) if isinstance(h, str)),
            "",
        )
        if not href:
            return ""
        return self._unwrap_link_url(href)

    @staticmethod
    def _unwrap_link_url(href: str) -> str:
        if "/link.php?" in href and "target=" in href:
            parsed = urlparse(href)
            params = parse_qs(parsed.query)
            target = params.get("target", [""])[0]
            if target:
                return unquote(target)
        return href

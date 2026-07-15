"""Ourbits 特殊 RSS 生成处理器。"""

from typing import cast
from urllib.parse import urlencode

from lxml import etree

from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.plugin_framework.context import PluginContext

from .base import SiteRssGenContext, SiteRssGenHandler, SiteRssGenResult


class Ourbits(SiteRssGenHandler):
    """Ourbits RSS 生成处理器。"""

    site_id = "ourbits"

    def __init__(self, plugin_ctx: PluginContext, rate_limiter, site_repo, config: dict | None = None):
        super().__init__(plugin_ctx, rate_limiter, site_repo)

    def generate(self, ctx: SiteRssGenContext) -> SiteRssGenResult:
        site = ctx.site
        site_def = self._plugin_ctx.site_engine.get_by_id(ctx.site_id)
        base_url = self._resolve_base_url(site_def, ctx)

        self._plugin_ctx.info(f"开始生成RSS站点：{site}")
        try:
            html_res = HttpClient(
                config=HttpClientConfig(proxy_url=ctx.proxy_url),
                rate_limiter=self._rate_limiter,
            ).get(
                url=f"{base_url}/getrss.php",
                headers={"User-Agent": ctx.ua},
                cookies=ctx.cookie,
            )
            html_text = html_res.text
        except Exception as e:
            self._plugin_ctx.warn(f"{site} RSS请求异常: {e}")
            return SiteRssGenResult.fail(site, SiteRssGenResult.SITE_UNREACHABLE)

        if "login.php" in html_text:
            return SiteRssGenResult.fail(site, SiteRssGenResult.COOKIE_EXPIRED)

        passkey = self._get_passkey(html_text)
        params = [
            ("inclbookmarked", "0"),
            ("https", "1"),
            ("icat", "1"),
            ("ismalldescr", "1"),
            ("isize", "1"),
            ("rows", "50"),
            ("search_mode", "1"),
            ("passkey", passkey),
        ]

        rss_link = self._build_link(base_url, params)
        self._plugin_ctx.debug(f"生成的rss: {rss_link}")

        if rss_link:
            self._save_rss_url(ctx.raw.get("id"), rss_link)
            self._plugin_ctx.info(f"{site} 生成RSS成功")
            return SiteRssGenResult.success(site)

        self._plugin_ctx.info(f"{site} 生成RSS失败")
        return SiteRssGenResult.fail(site, "未解析到RSS链接")

    @staticmethod
    def _get_passkey(html_text: str) -> str:
        if not html_text:
            return ""
        html = etree.HTML(html_text)
        if html is None:
            return ""
        return next(
            (href for href in cast(list, html.xpath('//input[@name="passkey"]/@value')) if isinstance(href, str)),
            "",
        )

    @staticmethod
    def _build_link(base_url: str, params: list) -> str:
        if not params or not base_url:
            return ""
        query_str = urlencode(params)
        return f"{base_url}/torrentrss.php?{query_str}"

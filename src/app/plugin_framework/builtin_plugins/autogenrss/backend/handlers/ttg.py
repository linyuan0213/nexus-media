"""TTG 特殊 RSS 生成处理器。"""

from typing import cast

from lxml import etree

from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.plugin_framework.context import PluginContext

from .base import SiteRssGenContext, SiteRssGenHandler, SiteRssGenResult


class TTG(SiteRssGenHandler):
    """TTG RSS 生成处理器。"""

    site_id = "ttg"

    def __init__(self, plugin_ctx: PluginContext, rate_limiter, site_repo, config: dict | None = None):
        super().__init__(plugin_ctx, rate_limiter, site_repo)

    def generate(self, ctx: SiteRssGenContext) -> SiteRssGenResult:
        site = ctx.site
        site_def = self._plugin_ctx.site_engine.get_by_id(ctx.site_id)
        base_url = self._resolve_base_url(site_def, ctx)

        params = {
            "c47": "47",
            "c28": "28",
            "c45": "45",
            "c49": "49",
            "c5": "5",
            "c105": "105",
            "c26": "26",
            "c104": "104",
            "c29": "29",
            "c46": "46",
            "c107": "107",
            "c110": "110",
            "c44": "44",
            "c106": "106",
            "c27": "27",
            "c43": "43",
            "c48": "48",
            "c33": "33",
            "c30": "30",
            "c31": "31",
            "c51": "51",
            "c52": "52",
            "c53": "53",
            "c54": "54",
            "c108": "108",
            "c109": "109",
            "c62": "62",
            "c63": "63",
            "c67": "67",
            "c69": "69",
            "c70": "70",
            "c73": "73",
            "c76": "76",
            "c75": "75",
            "c74": "74",
            "c87": "87",
            "c88": "88",
            "c99": "99",
            "c90": "90",
            "c77": "77",
            "c32": "32",
            "c56": "56",
            "c82": "82",
            "c83": "83",
            "c59": "59",
            "c57": "57",
            "c58": "58",
            "c103": "103",
            "c101": "101",
            "c60": "60",
            "c91": "91",
            "c84": "84",
            "c92": "92",
            "c93": "93",
            "c94": "94",
            "c95": "95",
            "c111": "111",
        }

        self._plugin_ctx.info(f"开始生成RSS站点：{site}")
        try:
            html_res = HttpClient(
                config=HttpClientConfig(proxy_url=ctx.proxy_url),
                rate_limiter=self._rate_limiter,
            ).get(
                url=f"{base_url}/rsstools.php",
                params=params,
                headers={"User-Agent": ctx.ua},
                cookies=ctx.cookie,
            )
            html_text = html_res.text
        except Exception as e:
            self._plugin_ctx.warn(f"{site} RSS请求异常: {e}")
            return SiteRssGenResult.fail(site, SiteRssGenResult.SITE_UNREACHABLE)

        if "login.php" in html_text:
            return SiteRssGenResult.fail(site, SiteRssGenResult.COOKIE_EXPIRED)

        rss_link = self._get_link(html_text)
        self._plugin_ctx.debug(f"生成的rss: {rss_link}")

        if rss_link:
            self._save_rss_url(ctx.raw.get("id"), rss_link)
            self._plugin_ctx.info(f"{site} 生成RSS成功")
            return SiteRssGenResult.success(site)

        self._plugin_ctx.info(f"{site} 生成RSS失败")
        return SiteRssGenResult.fail(site, "未解析到RSS链接")

    @staticmethod
    def _get_link(html_text: str) -> str:
        if not html_text:
            return ""
        html = etree.HTML(html_text)
        if html is None:
            return ""
        return next(
            (text for text in cast(list, html.xpath('//textarea[@id="trss"]/text()')) if isinstance(text, str)),
            "",
        )

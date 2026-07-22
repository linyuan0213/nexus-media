"""浏览器自动化通用 RSS 生成处理器。"""

from typing import cast

from lxml import etree

from app.infrastructure.chrome import BrowserSession
from app.plugin_framework.context import PluginContext
from app.sites.utils import is_logged_in
from app.utils.browser_mode import get_chrome_server_url

from .base import SiteRssGenContext, SiteRssGenHandler, SiteRssGenResult

DEFAULT_RSS_LINK_SELECTOR = '//a[contains(@href, "linktype=dl")]/@href'


class BrowserRssGenHandler(SiteRssGenHandler):
    """浏览器自动化通用 RSS 生成处理器。"""

    site_id = "__browser__"

    def __init__(self, plugin_ctx: PluginContext, rate_limiter, site_repo, site_cache, config: dict):
        super().__init__(plugin_ctx, rate_limiter, site_repo, site_cache)
        self._config = config

    def generate(self, ctx: SiteRssGenContext) -> SiteRssGenResult:
        site = ctx.site
        site_def = self._plugin_ctx.site_engine.get_by_id(ctx.site_id)
        home_url = self._resolve_base_url(site_def, ctx)
        path = self._config.get("path", "getrss.php").lstrip("/")
        url = f"{home_url}/{path}"

        server_url = get_chrome_server_url()
        if not server_url:
            return SiteRssGenResult.fail(site, "Chrome服务器未配置")

        self._plugin_ctx.info(f"开始浏览器RSS生成：{site}")
        try:
            with BrowserSession(site_key=site, server_url=server_url) as session:
                result = session.navigate(url, cookie=ctx.cookie)
                html_text = result.get("html", "")
                if not html_text:
                    return SiteRssGenResult.fail(site, "无法打开网站")

                if not is_logged_in(html_text):
                    return SiteRssGenResult.fail(site, "Cookie已失效")

                rss_link = self._parse_rss_link(html_text)
                self._plugin_ctx.debug(f"生成的rss: {rss_link}")
                if rss_link:
                    self._save_rss_url(ctx.raw.get("id"), rss_link)
                    return SiteRssGenResult.success(site)
                return SiteRssGenResult.fail(site, "未解析到RSS链接")
        except Exception as e:
            self._plugin_ctx.warn(f"{site} 浏览器RSS生成异常: {e}")
            return SiteRssGenResult.fail(site, str(e))

    def _parse_rss_link(self, html_text: str) -> str:
        if not html_text:
            return ""
        selector = self._config.get("rss_link_selector") or DEFAULT_RSS_LINK_SELECTOR
        html = etree.HTML(html_text)
        if html is None:
            return ""
        return next(
            (href for href in cast(list, html.xpath(selector)) if isinstance(href, str)),
            "",
        )

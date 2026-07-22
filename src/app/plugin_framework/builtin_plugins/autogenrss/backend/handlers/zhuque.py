"""ZhuQue 特殊 RSS 生成处理器。"""

from typing import cast

from lxml import etree

from app.infrastructure.http.auth import CookieAuth
from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.plugin_framework.context import PluginContext

from .base import SiteRssGenContext, SiteRssGenHandler, SiteRssGenResult


class ZhuQue(SiteRssGenHandler):
    """ZhuQue RSS 生成处理器。"""

    site_id = "tnode"

    def __init__(self, plugin_ctx: PluginContext, rate_limiter, site_repo, site_cache, config: dict | None = None):
        super().__init__(plugin_ctx, rate_limiter, site_repo, site_cache)

    def generate(self, ctx: SiteRssGenContext) -> SiteRssGenResult:
        site = ctx.site
        site_def = self._plugin_ctx.site_engine.get_by_id(ctx.site_id)
        base_url = self._resolve_base_url(site_def, ctx)
        auth = CookieAuth(ctx.cookie) if ctx.cookie else None

        self._plugin_ctx.info(f"开始生成RSS站点：{site}")
        try:
            html_res = HttpClient(
                config=HttpClientConfig(proxy_url=ctx.proxy_url),
                rate_limiter=self._rate_limiter,
            ).get(url=base_url, headers={"User-Agent": ctx.ua}, auth=auth)
            html_text = html_res.text
        except Exception as e:
            self._plugin_ctx.warn(f"{site} RSS请求异常: {e}")
            return SiteRssGenResult.fail(site, SiteRssGenResult.SITE_UNREACHABLE)

        if "login.php" in html_text:
            return SiteRssGenResult.fail(site, SiteRssGenResult.COOKIE_EXPIRED)

        html = etree.HTML(html_text)
        if html is None:
            return SiteRssGenResult.fail(site, "解析页面失败")

        x_csrf_token_list = cast(list, html.xpath("//meta[@name='x-csrf-token']/@content"))
        x_csrf_token = x_csrf_token_list[0] if x_csrf_token_list else None
        if not x_csrf_token:
            return SiteRssGenResult.fail(site, "未获取到CSRF令牌")

        headers = {
            "x-csrf-token": str(x_csrf_token),
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": ctx.ua,
        }
        try:
            security_res = HttpClient(
                config=HttpClientConfig(proxy_url=ctx.proxy_url),
                rate_limiter=self._rate_limiter,
            ).get(url=f"{base_url}/api/user/getSecurityInfo", headers=headers, auth=auth)
            json_data = security_res.json()
        except Exception as e:
            self._plugin_ctx.warn(f"{site} 安全信息请求异常: {e}")
            return SiteRssGenResult.fail(site, SiteRssGenResult.SITE_UNREACHABLE)

        rss_link = ""
        if json_data.get("status") == 200:
            data = json_data.get("data", {})
            rss_key = data.get("rssKey")
            torrent_key = data.get("torrentKey")
            if rss_key and torrent_key:
                rss_link = f"{base_url}/api/torrent/rss/{rss_key}/{torrent_key}"
                self._plugin_ctx.debug(f"生成的rss: {rss_link}")

        if rss_link:
            self._save_rss_url(ctx.raw.get("id"), rss_link)
            self._plugin_ctx.info(f"{site} 生成RSS成功")
            return SiteRssGenResult.success(site)

        self._plugin_ctx.info(f"{site} 生成RSS失败")
        return SiteRssGenResult.fail(site, "未解析到RSS链接")

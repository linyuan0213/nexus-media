"""Star-space 特殊 RSS 生成处理器。"""

from typing import cast

from lxml import etree

from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.plugin_framework.context import PluginContext

from .base import SiteRssGenContext, SiteRssGenHandler, SiteRssGenResult


class Starspace(SiteRssGenHandler):
    """Star-space RSS 生成处理器。"""

    site_id = "star-space"

    def __init__(self, plugin_ctx: PluginContext, rate_limiter, site_repo, config: dict | None = None):
        super().__init__(plugin_ctx, rate_limiter, site_repo)

    def generate(self, ctx: SiteRssGenContext) -> SiteRssGenResult:
        site = ctx.site
        site_def = self._plugin_ctx.site_engine.get_by_id(ctx.site_id)
        base_url = self._resolve_base_url(site_def, ctx)

        create_url = f"{base_url}/p_rss/rss_create.php"
        act_url = f"{base_url}/p_rss/rss_act.php"

        self._plugin_ctx.info(f"开始生成RSS站点：{site}")
        try:
            html_res = HttpClient(
                config=HttpClientConfig(proxy_url=ctx.proxy_url),
                rate_limiter=self._rate_limiter,
            ).get(url=create_url, headers={"User-Agent": ctx.ua}, cookies=ctx.cookie)
            html_text = html_res.text
        except Exception as e:
            self._plugin_ctx.warn(f"{site} RSS请求异常: {e}")
            return SiteRssGenResult.fail(site, SiteRssGenResult.SITE_UNREACHABLE)

        if "login_act.php" in html_text:
            return SiteRssGenResult.fail(site, SiteRssGenResult.COOKIE_EXPIRED)

        rss_link = self._get_rss_link(html_text)
        if not rss_link:
            data = {"cat": "", "media": "", "btn_add": "创建RSS"}
            headers = {
                "accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
                    "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
                ),
                "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,ja;q=0.7",
                "content-type": "application/x-www-form-urlencoded",
                "origin": base_url,
                "referer": create_url,
                "user-agent": ctx.ua,
            }
            try:
                post_res = HttpClient(
                    config=HttpClientConfig(proxy_url=ctx.proxy_url),
                    rate_limiter=self._rate_limiter,
                ).post(url=act_url, data=data, headers=headers, cookies=ctx.cookie)
            except Exception as e:
                self._plugin_ctx.warn(f"{site} RSS创建请求异常: {e}")
                return SiteRssGenResult.fail(site, SiteRssGenResult.SITE_UNREACHABLE)

            if "操作成功" in post_res.text:
                try:
                    html_res = HttpClient(
                        config=HttpClientConfig(proxy_url=ctx.proxy_url),
                        rate_limiter=self._rate_limiter,
                    ).get(
                        url=create_url,
                        headers={"User-Agent": ctx.ua},
                        cookies=ctx.cookie,
                    )
                    html_text = html_res.text
                except Exception as e:
                    self._plugin_ctx.warn(f"{site} RSS刷新请求异常: {e}")
                    return SiteRssGenResult.fail(site, SiteRssGenResult.SITE_UNREACHABLE)
                rss_link = self._get_rss_link(html_text)

        self._plugin_ctx.debug(f"生成的rss: {rss_link}")
        if rss_link:
            self._save_rss_url(ctx.raw.get("id"), rss_link)
            self._plugin_ctx.info(f"{site} 生成RSS成功")
            return SiteRssGenResult.success(site)

        self._plugin_ctx.info(f"{site} 生成RSS失败")
        return SiteRssGenResult.fail(site, "未解析到RSS链接")

    @staticmethod
    def _get_rss_link(html_text: str) -> str:
        if not html_text:
            return ""
        html = etree.HTML(html_text)
        if html is None:
            return ""
        return next(
            (
                href
                for href in cast(list, html.xpath('//a[contains(@href, "rss.php?key=")]/@href'))
                if isinstance(href, str)
            ),
            "",
        )

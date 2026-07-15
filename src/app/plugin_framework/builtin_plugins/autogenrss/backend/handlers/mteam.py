"""M-Team 特殊 RSS 生成处理器。"""

from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.plugin_framework.context import PluginContext
from app.utils.json_utils import JsonUtils

from .base import SiteRssGenContext, SiteRssGenHandler, SiteRssGenResult


class Mteam(SiteRssGenHandler):
    """M-Team RSS 生成处理器。"""

    site_id = "mteam"

    def __init__(self, plugin_ctx: PluginContext, rate_limiter, site_repo, config: dict | None = None):
        super().__init__(plugin_ctx, rate_limiter, site_repo)

    def generate(self, ctx: SiteRssGenContext) -> SiteRssGenResult:
        site = ctx.site
        site_def = self._plugin_ctx.site_engine.get_by_id(ctx.site_id)
        base_url = self._resolve_api_base(site_def)

        ua = ctx.ua
        headers = dict(ctx.headers) if ctx.headers else {}
        headers.update({"contentType": "application/json;charset=UTF-8", "User-Agent": ua})

        url = f"{base_url}/api/rss/genlink"
        data = {"labels": 0, "tkeys": ["ttitle", "tcat", "tsmalldescr", "tsize"], "pageSize": 50}
        data = JsonUtils.dumps(data, separators=(",", ":"))

        self._plugin_ctx.debug(f"{site} M-Team RSS请求: {url}")
        try:
            res = HttpClient(
                config=HttpClientConfig(proxy_url=ctx.proxy_url),
                rate_limiter=self._rate_limiter,
            ).post(url=url, data=data, headers=headers)
            json_data = res.json()
        except Exception as e:
            self._plugin_ctx.warn(f"{site} M-Team RSS请求异常: {e}")
            return SiteRssGenResult.fail(site, SiteRssGenResult.SITE_UNREACHABLE)

        rss_link = ""
        if json_data.get("message") == "SUCCESS":
            rss_link = json_data.get("data", {}).get("dlUrl", "")
            self._plugin_ctx.debug(f"生成的rss: {rss_link}")

        if rss_link:
            self._save_rss_url(ctx.raw.get("id"), rss_link)
            self._plugin_ctx.info(f"{site} 生成RSS成功")
            return SiteRssGenResult.success(site)

        self._plugin_ctx.info(f"{site} 生成RSS失败")
        return SiteRssGenResult.fail(site, "未解析到RSS链接")

    def _resolve_api_base(self, site_def) -> str:
        if site_def and site_def.api and site_def.api.base_url:
            return site_def.api.base_url.rstrip("/")
        return "https://api.m-team.io"

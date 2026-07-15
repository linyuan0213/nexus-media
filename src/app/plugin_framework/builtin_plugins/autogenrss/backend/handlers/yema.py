"""YemaPT 特殊 RSS 生成处理器。"""

from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.plugin_framework.context import PluginContext
from app.utils.json_utils import JsonUtils

from .base import SiteRssGenContext, SiteRssGenHandler, SiteRssGenResult


class YemaPT(SiteRssGenHandler):
    """YemaPT RSS 生成处理器。"""

    site_id = "yemapt"

    def __init__(self, plugin_ctx: PluginContext, rate_limiter, site_repo, config: dict | None = None):
        super().__init__(plugin_ctx, rate_limiter, site_repo)

    def generate(self, ctx: SiteRssGenContext) -> SiteRssGenResult:
        site = ctx.site
        site_def = self._plugin_ctx.site_engine.get_by_id(ctx.site_id)
        base_url = self._resolve_api_base(site_def, ctx)

        headers = {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "user-agent": ctx.ua,
        }
        if ctx.headers and isinstance(ctx.headers, dict):
            headers.update(ctx.headers)

        url = f"{base_url}/api/rss/generateRssUrl"
        data = {
            "categoryIdList": [],
            "withShortDesc": True,
            "withSize": True,
            "showPromotion": False,
            "pageSize": 50,
        }
        data = JsonUtils.dumps(data, separators=(",", ":"))

        self._plugin_ctx.debug(f"{site} YemaPT RSS请求: {url}")
        try:
            res = HttpClient(
                config=HttpClientConfig(proxy_url=ctx.proxy_url),
                rate_limiter=self._rate_limiter,
            ).post(url=url, data=data, headers=headers, cookies=ctx.cookie)
            json_data = res.json()
        except Exception as e:
            self._plugin_ctx.warn(f"{site} YemaPT RSS请求异常: {e}")
            return SiteRssGenResult.fail(site, SiteRssGenResult.SITE_UNREACHABLE)

        rss_link = ""
        if json_data.get("success"):
            rss_link = json_data.get("data", "")
            self._plugin_ctx.debug(f"生成的rss: {rss_link}")

        if rss_link:
            self._save_rss_url(ctx.raw.get("id"), rss_link)
            self._plugin_ctx.info(f"{site} 生成RSS成功")
            return SiteRssGenResult.success(site)

        self._plugin_ctx.info(f"{site} 生成RSS失败")
        return SiteRssGenResult.fail(site, "未解析到RSS链接")

    def _resolve_api_base(self, site_def, ctx: SiteRssGenContext) -> str:
        if site_def and site_def.api and site_def.api.base_url:
            return site_def.api.base_url.rstrip("/")
        if site_def and site_def.domain:
            domain = site_def.domain
            if not domain.startswith(("http://", "https://")):
                domain = f"https://{domain}"
            return domain.rstrip("/")
        return "https://www.yemapt.org"

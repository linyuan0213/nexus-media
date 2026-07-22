"""YemaPT RSS 生成处理器。"""

from urllib.parse import urlencode

from app.infrastructure.http.auth import CookieAuth
from app.plugin_framework.context import PluginContext
from app.utils.json_utils import JsonUtils

from .base import SiteRssGenContext, SiteRssGenHandler, SiteRssGenResult


class YemaPT(SiteRssGenHandler):
    site_id = "yemapt"

    def __init__(self, plugin_ctx: PluginContext, rate_limiter, site_repo, site_cache, config: dict | None = None):
        super().__init__(plugin_ctx, rate_limiter, site_repo, site_cache)

    def generate(self, ctx: SiteRssGenContext) -> SiteRssGenResult:
        site = ctx.site
        site_def = self._plugin_ctx.site_engine.get_by_id(ctx.site_id)
        base_url = self._resolve_api_base(site_def)

        if not ctx.cookie:
            return SiteRssGenResult.fail(site, SiteRssGenResult.COOKIE_EXPIRED)

        auth = CookieAuth(ctx.cookie)
        headers = {
            "User-Agent": ctx.ua,
            "Referer": base_url + "/",
        }

        client = self._http_client(ctx)
        try:
            res = client.get(
                url=f"{base_url}/api/rss/fetchRssPageConfig",
                headers=headers,
                auth=auth,
            )
            json_data = res.json()
        except Exception as e:
            self._plugin_ctx.warn(f"{site} YemaPT RSS请求异常: {e}")
            return SiteRssGenResult.fail(site, SiteRssGenResult.SITE_UNREACHABLE)

        if not json_data.get("success"):
            return SiteRssGenResult.fail(site, f"接口返回 {JsonUtils.dumps(json_data)}")

        rss_token = json_data.get("data", {}).get("rssToken", "")
        if not rss_token:
            return SiteRssGenResult.fail(site, "未获取到 rssToken")

        params = {
            "rssToken": rss_token,
            "withShortDesc": "true",
            "withSize": "true",
            "showPromotion": "false",
            "pageSize": 100,
        }
        rss_link = f"{base_url}/api/rss/torrents?{urlencode(params)}"
        self._plugin_ctx.debug(f"生成的rss: {rss_link}")

        self._save_rss_url(ctx.raw.get("id"), rss_link)
        self._plugin_ctx.info(f"{site} 生成RSS成功")
        return SiteRssGenResult.success(site)

    @staticmethod
    def _resolve_api_base(site_def) -> str:
        if site_def and site_def.api and site_def.api.base_url:
            return site_def.api.base_url.rstrip("/")
        return "https://www.yemapt.org"

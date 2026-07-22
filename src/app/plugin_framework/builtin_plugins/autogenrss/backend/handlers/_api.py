"""API 站点通用 RSS 生成处理器。"""

from app.infrastructure.http.auth import ApiKeyAuth, BearerAuth, CookieAuth
from app.plugin_framework.context import PluginContext
from app.utils import StringUtils
from app.utils.json_utils import JsonUtils

from .base import SiteRssGenContext, SiteRssGenHandler, SiteRssGenResult


class ApiRssGenHandler(SiteRssGenHandler):
    """API 站点通用 RSS 生成处理器。"""

    site_id = "__api__"

    def __init__(self, plugin_ctx: PluginContext, rate_limiter, site_repo, config: dict):
        super().__init__(plugin_ctx, rate_limiter, site_repo)
        self._config = config

    def generate(self, ctx: SiteRssGenContext) -> SiteRssGenResult:
        site_def = self._plugin_ctx.site_engine.get_by_id(ctx.site_id)
        base_url = self._resolve_api_base(site_def, ctx)
        endpoint = self._config.get("endpoint", {})
        path = endpoint.get("path", "").lstrip("/")
        url = f"{base_url}/{path}" if path else base_url
        method = endpoint.get("method", "POST")
        body = endpoint.get("body")
        headers = self._build_headers(ctx)

        auth, extra_headers = self._resolve_auth(ctx, site_def)
        if isinstance(auth, SiteRssGenResult):
            return auth
        headers.update(extra_headers)

        self._plugin_ctx.debug(f"{ctx.site} API RSS请求: {method} {url}")
        client = self._http_client(ctx)
        try:
            if method.upper() == "POST":
                res = client.post(url=url, json=body, headers=headers, auth=auth)
            else:
                res = client.get(url=url, params=body, headers=headers, auth=auth)
        except Exception as e:
            self._plugin_ctx.warn(f"{ctx.site} API RSS请求异常: {e}")
            return SiteRssGenResult.fail(ctx.site, SiteRssGenResult.SITE_UNREACHABLE)

        return self._check_response(res, ctx)

    def _resolve_api_base(self, site_def, ctx: SiteRssGenContext) -> str:
        if site_def and site_def.api and site_def.api.base_url:
            return site_def.api.base_url.rstrip("/")
        return StringUtils.get_base_url(ctx.site_url).rstrip("/")

    def _resolve_auth(self, ctx: SiteRssGenContext, site_def=None):
        auth_type = self._config.get("auth")
        if auth_type == "api_key" or (auth_type is None and ctx.api_key):
            if not ctx.api_key:
                return SiteRssGenResult.fail(ctx.site, "未配置api_key"), {}
            header_name = ctx.api_key_header or "x-api-key"
            if not ctx.api_key_header and site_def and site_def.api and site_def.api.auth:
                header_name = site_def.api.auth.get("header_name", header_name)
            return ApiKeyAuth(header_name, ctx.api_key), {}
        if auth_type == "bearer" or (auth_type is None and ctx.bearer_token):
            if not ctx.bearer_token:
                return SiteRssGenResult.fail(ctx.site, "未配置bearer_token"), {}
            return BearerAuth(ctx.bearer_token), {}
        if auth_type in ("cookie", "cookie_raw") or (auth_type is None and ctx.cookie):
            if not ctx.cookie:
                return SiteRssGenResult.fail(ctx.site, SiteRssGenResult.COOKIE_EXPIRED), {}
            return CookieAuth(ctx.cookie), {}
        return None, {}

    def _check_response(self, res, ctx: SiteRssGenContext) -> SiteRssGenResult:
        text = res.text
        success_path = self._config.get("json_success_path")
        success_value = self._config.get("json_success_value")
        already_path = self._config.get("json_already_path")
        already_value = self._config.get("json_already_value")
        rss_link_path = self._config.get("json_rss_link_path")

        try:
            data = JsonUtils.loads(text)
        except Exception:
            if success_path or already_path or rss_link_path:
                return SiteRssGenResult.fail(ctx.site, "解析JSON响应失败")
            data = {}
            decoded_text = text
        else:
            decoded_text = JsonUtils.dumps(data, ensure_ascii=False) if data else text

        if success_path and data.get(success_path) == success_value:
            return SiteRssGenResult.success(ctx.site)
        if already_path and data.get(already_path) == already_value:
            return SiteRssGenResult.success(ctx.site, "已生成")

        rss_link = self._extract_rss_link(data, rss_link_path) if rss_link_path else ""
        if rss_link:
            self._save_rss_url(ctx.raw.get("id"), rss_link)
            return SiteRssGenResult.success(ctx.site)

        for marker in self._config.get("success_markers", []):
            if marker in decoded_text:
                return SiteRssGenResult.success(ctx.site)
        for marker in self._config.get("already_markers", []):
            if marker in decoded_text:
                return SiteRssGenResult.success(ctx.site, "已生成")

        return SiteRssGenResult.fail(ctx.site, f"接口返回 {decoded_text[:200]}")

    def _extract_rss_link(self, data: dict, path: str) -> str:
        value = data
        for key in path.split("."):
            if not isinstance(value, dict):
                return ""
            value = value.get(key, "")
        return str(value) if value else ""

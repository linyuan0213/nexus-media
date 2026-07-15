"""API 站点通用签到处理器。"""

from app.infrastructure.http.auth import BearerAuth, CookieAuth
from app.utils import StringUtils
from app.utils.json_utils import JsonUtils

from ..credentials import CredentialResolver
from .base import SigninResult, SiteSigninContext, SiteSigninHandler


class ApiSigninHandler(SiteSigninHandler):
    """API 站点通用处理器。"""

    site_id = "__api__"

    def __init__(self, plugin_ctx, rate_limiter, config: dict):
        super().__init__(plugin_ctx, rate_limiter)
        self._config = config

    def signin(self, ctx: SiteSigninContext) -> SigninResult:
        site_def = self._plugin_ctx.site_engine.get_by_id(ctx.site_id)
        base_url = self._resolve_api_base(site_def, ctx)
        path = self._config.get("endpoint", {}).get("path", "").lstrip("/")
        url = f"{base_url}/{path}" if path else base_url
        method = self._config.get("endpoint", {}).get("method", "POST")
        body = self._config.get("endpoint", {}).get("body")
        headers = self._build_headers(ctx)

        auth, extra_headers = self._resolve_auth(ctx)
        if isinstance(auth, SigninResult):
            self._plugin_ctx.debug(f"{ctx.site} API 凭据解析失败: {auth.msg}")
            return auth
        headers.update(extra_headers)

        self._plugin_ctx.debug(f"{ctx.site} API 签到请求: {method} {url}")
        client = self._http_client(ctx)
        try:
            if method.upper() == "POST":
                res = client.post(url=url, json=body, headers=headers, auth=auth)
            else:
                res = client.get(url=url, params=body, headers=headers, auth=auth)
        except Exception as e:
            self._plugin_ctx.warn(f"{ctx.site} API 签到请求异常: {e}")
            return SigninResult.fail(ctx.site, SigninResult.SITE_UNREACHABLE)

        return self._check_response(res, ctx)

    def _resolve_api_base(self, site_def, ctx: SiteSigninContext) -> str:
        if site_def and site_def.api and site_def.api.base_url:
            return site_def.api.base_url.rstrip("/")
        return StringUtils.get_base_url(ctx.site_url).rstrip("/")

    def _build_headers(self, ctx: SiteSigninContext) -> dict:
        headers: dict = {}
        cfg_headers = self._config.get("headers")
        if cfg_headers and isinstance(cfg_headers, dict):
            headers.update(cfg_headers)
        if ctx.headers and isinstance(ctx.headers, dict):
            headers.update(ctx.headers)
        if ctx.ua:
            headers.setdefault("User-Agent", ctx.ua)
        return headers

    def _resolve_auth(self, ctx: SiteSigninContext):
        auth_type = self._config.get("auth")
        auth_source = self._config.get("auth_source")

        if auth_source:
            resolver = CredentialResolver(ctx.raw)
            token, need_sync = resolver.resolve(auth_source)
            if need_sync:
                CredentialResolver.sync_local_storage(self._plugin_ctx.hook_system)
                token = resolver.resolve_after_sync(auth_source)
            if token:
                return self._wrap_auth(ctx, auth_type, token)
            self._plugin_ctx.debug(f"{ctx.site} auth_source 未提取到 token，尝试站点默认凭据")

        if auth_type == "api_key" or (auth_type is None and ctx.api_key):
            if not ctx.api_key:
                return SigninResult.fail(ctx.site, "未配置 api_key"), {}
            header_name = ctx.api_key_header or "X-Api-Key"
            return None, {header_name: ctx.api_key}

        if auth_type == "bearer" or (auth_type is None and ctx.bearer_token):
            if not ctx.bearer_token:
                return SigninResult.fail(ctx.site, "未配置 bearer_token"), {}
            return BearerAuth(ctx.bearer_token), {}

        if auth_type in ("cookie_parsed", "cookie_raw") or (auth_type is None and ctx.cookie):
            if not ctx.cookie:
                return SigninResult.fail(ctx.site, SigninResult.COOKIE_EXPIRED), {}
            if auth_type == "cookie_raw":
                return CookieAuth(ctx.cookie), {}
            return CookieAuth(CookieAuth._parse_cookies(ctx.cookie)), {}

        return None, {}

    def _wrap_auth(self, ctx: SiteSigninContext, auth_type: str | None, token: str | None):
        if auth_type == "bearer":
            if not token:
                return SigninResult.fail(ctx.site, "未配置 bearer_token"), {}
            return BearerAuth(token), {}
        if auth_type == "api_key":
            if not token:
                return SigninResult.fail(ctx.site, "未配置 api_key"), {}
            header_name = ctx.api_key_header or "X-Api-Key"
            return None, {header_name: token}
        if auth_type in ("cookie_parsed", "cookie_raw"):
            if not token:
                return SigninResult.fail(ctx.site, SigninResult.COOKIE_EXPIRED), {}
            if auth_type == "cookie_parsed":
                return CookieAuth(CookieAuth._parse_cookies(token)), {}
            return CookieAuth(token), {}
        return None, {}

    def _check_response(self, res, ctx: SiteSigninContext) -> SigninResult:
        text = res.text
        success_path = self._config.get("json_success_path")
        success_value = self._config.get("json_success_value")
        already_path = self._config.get("json_already_path")
        already_value = self._config.get("json_already_value")

        if success_path or already_path:
            try:
                data = JsonUtils.loads(text)
            except Exception:
                return SigninResult.fail(ctx.site, "解析 JSON 响应失败")
            if success_path and data.get(success_path) == success_value:
                return SigninResult.success(ctx.site)
            if already_path and data.get(already_path) == already_value:
                return SigninResult.already(ctx.site)

        for marker in self._config.get("success_markers", []):
            if marker in text:
                return SigninResult.success(ctx.site)
        for marker in self._config.get("already_markers", []):
            if marker in text:
                return SigninResult.already(ctx.site)

        return SigninResult.fail(ctx.site, f"接口返回 {text[:200]}")

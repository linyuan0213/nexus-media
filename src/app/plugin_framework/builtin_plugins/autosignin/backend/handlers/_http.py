"""HTML 站点通用 HTTP 签到处理器。"""

import re

from app.infrastructure.http.auth import CookieAuth
from app.utils import StringUtils

from .base import SigninResult, SiteSigninContext, SiteSigninHandler

DEFAULT_SUCCESS_MARKERS = [
    "签到成功",
    "此次签到您获得",
    "获得.*魔力值",
    "获得.*积分",
    "已获取",
]

DEFAULT_ALREADY_MARKERS = [
    "今日已签到",
    "今日已签",
    "已经签到",
    "请不要重复签到",
    "签到已得",
    "重复签到",
    "今天已经签过到了",
]


class HttpSigninHandler(SiteSigninHandler):
    """HTML 站点通用 HTTP 处理器。"""

    site_id = "__http__"

    def __init__(self, plugin_ctx, rate_limiter, config: dict):
        super().__init__(plugin_ctx, rate_limiter)
        self._config = config
        self._success_markers = config.get("success_markers") or DEFAULT_SUCCESS_MARKERS
        self._already_markers = config.get("already_markers") or DEFAULT_ALREADY_MARKERS
        self._success_absent_markers = config.get("success_absent_markers", [])
        self._already_absent_markers = config.get("already_absent_markers", [])

    def signin(self, ctx: SiteSigninContext) -> SigninResult:
        if not ctx.site_url:
            return SigninResult.custom(True, "")

        site_def = self._plugin_ctx.site_engine.get_by_id(ctx.site_id)
        base_url = self._resolve_base_url(site_def, ctx)
        path = self._config.get("path", "").lstrip("/")
        url = f"{base_url}/{path}" if path else base_url
        method = self._config.get("method", "get")
        data = self._config.get("data")
        headers = self._build_headers(ctx)

        auth = self._resolve_auth(ctx)
        if isinstance(auth, SigninResult):
            self._plugin_ctx.debug(f"{ctx.site} HTTP 凭据解析失败: {auth.msg}")
            return auth

        self._plugin_ctx.debug(f"{ctx.site} HTTP 签到请求: {method.upper()} {url}")
        client = self._http_client(ctx)
        try:
            if method.upper() == "POST":
                res = client.post(url=url, data=data, headers=headers, auth=auth)
            else:
                res = client.get(url=url, params=data, headers=headers, auth=auth)
        except Exception as e:
            self._plugin_ctx.warn(f"{ctx.site} HTTP 签到请求异常: {e}")
            return SigninResult.fail(ctx.site, SigninResult.SITE_UNREACHABLE)

        if cookie_result := self._check_cookie(res.text, ctx.site):
            return cookie_result

        text = res.text
        if self._match_markers(text, self._success_markers):
            return SigninResult.success(ctx.site)
        if self._match_markers(text, self._already_markers):
            return SigninResult.already(ctx.site)
        if self._match_absent_markers(text, self._success_absent_markers):
            return SigninResult.success(ctx.site)
        if self._match_absent_markers(text, self._already_absent_markers):
            return SigninResult.already(ctx.site)

        return SigninResult.fail(ctx.site, f"签到接口返回 {text[:200]}")

    @staticmethod
    def _match_absent_markers(text: str, markers: list[str]) -> bool:
        return bool(markers and not any(re.search(marker, text) for marker in markers))

    def _resolve_base_url(self, site_def, ctx: SiteSigninContext) -> str:
        if site_def and site_def.domain:
            domain = site_def.domain
            if not domain.startswith(("http://", "https://")):
                domain = f"https://{domain}"
            return domain.rstrip("/")
        return StringUtils.get_base_url(ctx.site_url).rstrip("/")

    def _build_headers(self, ctx: SiteSigninContext) -> dict:
        headers: dict = {}
        if ctx.headers and isinstance(ctx.headers, dict):
            headers.update(ctx.headers)
        if ctx.ua:
            headers.setdefault("User-Agent", ctx.ua)
        return headers

    def _resolve_auth(self, ctx: SiteSigninContext):
        auth_type = self._config.get("auth")
        if auth_type in ("cookie_parsed", "cookie_raw") or (auth_type is None and ctx.cookie):
            if not ctx.cookie:
                return SigninResult.fail(ctx.site, SigninResult.COOKIE_EXPIRED)
            if auth_type == "cookie_raw":
                return CookieAuth(ctx.cookie)
            return CookieAuth(CookieAuth._parse_cookies(ctx.cookie))
        return None

    @staticmethod
    def _match_markers(text: str, markers: list[str]) -> bool:
        for marker in markers:
            if re.search(marker, text):
                return True
        return False

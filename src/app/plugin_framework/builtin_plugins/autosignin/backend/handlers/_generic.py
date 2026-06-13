"""通用匹配兜底处理器 — 适用于绝大多数纯字符串匹配型站点。"""

import re

from app.infrastructure.http.auth import CookieAuth

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


class GenericSigninHandler(SiteSigninHandler):
    """通用匹配兜底处理器。默认使用数据库 cookie 认证。"""

    site_url = "__generic__"

    def __init__(
        self,
        plugin_ctx,
        rate_limiter,
        success_markers: list[str] | None = None,
        already_markers: list[str] | None = None,
    ):
        super().__init__(plugin_ctx, rate_limiter)
        self._success_markers = success_markers or DEFAULT_SUCCESS_MARKERS
        self._already_markers = already_markers or DEFAULT_ALREADY_MARKERS

    def signin(self, ctx: SiteSigninContext) -> SigninResult:
        if not ctx.site_url:
            return SigninResult.custom(True, "")

        client = self._http_client(ctx)
        auth = CookieAuth(ctx.cookie) if ctx.cookie else None
        headers = self._build_headers(ctx)

        try:
            res = client.get(url=ctx.site_url, headers=headers, auth=auth)
        except Exception:
            return SigninResult.fail(ctx.site, SigninResult.SITE_UNREACHABLE)

        if cookie_result := self._check_cookie(res.text, ctx.site):
            return cookie_result

        text = res.text
        if self._match_markers(text, self._success_markers):
            return SigninResult.success(ctx.site)
        if self._match_markers(text, self._already_markers):
            return SigninResult.already(ctx.site)

        return SigninResult.fail(ctx.site, f"签到接口返回 {text[:200]}")

    def _build_headers(self, ctx: SiteSigninContext) -> dict:
        headers: dict = {}
        if ctx.headers and isinstance(ctx.headers, dict):
            headers.update(ctx.headers)
        if ctx.ua:
            headers.setdefault("User-Agent", ctx.ua)
        return headers

    @staticmethod
    def _match_markers(text: str, markers: list[str]) -> bool:
        for marker in markers:
            if re.search(marker, text):
                return True
        return False

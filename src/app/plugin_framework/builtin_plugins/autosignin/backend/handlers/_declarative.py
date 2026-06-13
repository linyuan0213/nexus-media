"""声明式配置处理器 — 支持 method / auth_type / auth_source / markers 精确控制。"""

import re
from dataclasses import dataclass, field
from typing import Any

from app.infrastructure.http.auth import BearerAuth, CookieAuth
from app.utils import StringUtils
from app.utils.json_utils import JsonUtils

from ..credentials import CredentialResolver
from .base import SigninResult, SiteSigninContext, SiteSigninHandler


@dataclass
class DeclarativeSiteConfig:
    site_url: str
    method: str = "get"
    path: str = ""
    data: dict | None = None
    headers: dict | None = None
    auth_type: str = "cookie_parsed"
    auth_source: dict | None = None
    success_markers: list[str] = field(default_factory=list)
    already_markers: list[str] = field(default_factory=list)
    cookie_check: bool = True
    response_type: str = "html"
    json_success_path: str = ""
    json_success_value: Any = None


class DeclarativeSigninHandler(SiteSigninHandler):
    def __init__(self, plugin_ctx, rate_limiter, config: DeclarativeSiteConfig):
        super().__init__(plugin_ctx, rate_limiter)
        self._config = config

    def signin(self, ctx: SiteSigninContext) -> SigninResult:
        auth, extra_headers = self._resolve_auth(ctx)
        if isinstance(auth, SigninResult):
            return auth

        client = self._http_client(ctx)
        url = self._build_url(ctx)
        headers = self._build_headers(ctx, extra_headers)

        try:
            if self._config.method == "post":
                res = client.post(url=url, data=self._config.data, headers=headers, auth=auth)
            else:
                res = client.get(url=url, headers=headers, auth=auth)
        except Exception:
            return SigninResult.fail(ctx.site, SigninResult.SITE_UNREACHABLE)

        if self._config.cookie_check:
            if cookie_result := self._check_cookie(res.text, ctx.site):
                return cookie_result

        if self._config.response_type == "json":
            return self._check_json_response(res, ctx)

        text = res.text
        for marker in self._config.success_markers:
            if re.search(marker, text):
                return SigninResult.success(ctx.site)
        for marker in self._config.already_markers:
            if re.search(marker, text):
                return SigninResult.already(ctx.site)

        return SigninResult.fail(ctx.site, f"签到接口返回 {text[:200]}")

    def _resolve_auth(self, ctx: SiteSigninContext):
        resolver = CredentialResolver(ctx.raw)

        if self._config.auth_source is None:
            token = self._default_db_field(ctx)
        else:
            token, need_sync = resolver.resolve(self._config.auth_source)
            if need_sync:
                CredentialResolver.sync_local_storage(self._plugin_ctx.hook_system)
                token = resolver.resolve_after_sync(self._config.auth_source)

        return self._wrap_auth(ctx, token)

    def _default_db_field(self, ctx: SiteSigninContext) -> str | None:
        if self._config.auth_type in ("cookie_parsed", "cookie_raw"):
            return ctx.cookie
        if self._config.auth_type == "bearer":
            return ctx.bearer_token
        if self._config.auth_type == "apikey":
            return ctx.api_key
        return None

    def _wrap_auth(self, ctx: SiteSigninContext, token: str | None):
        if self._config.auth_type in ("cookie_parsed", "cookie_raw"):
            if not token:
                return SigninResult.fail(ctx.site, SigninResult.COOKIE_EXPIRED), {}
            if self._config.auth_type == "cookie_parsed":
                return CookieAuth._parse_cookies(token), {}
            return CookieAuth(token), {}

        if self._config.auth_type == "bearer":
            if not token:
                return SigninResult.fail(ctx.site, "未配置 bearer_token"), {}
            return BearerAuth(token), {}

        if self._config.auth_type == "apikey":
            if not token:
                return SigninResult.fail(ctx.site, "未配置 api_key"), {}
            header_name = ctx.api_key_header or "X-Api-Key"
            return None, {header_name: token}

        return None, {}

    def _build_url(self, ctx: SiteSigninContext) -> str:
        if not self._config.path:
            return ctx.site_url
        base = StringUtils.get_base_url(ctx.site_url).rstrip("/")
        return f"{base}/{self._config.path.lstrip('/')}"

    def _build_headers(self, ctx: SiteSigninContext, extra: dict) -> dict:
        headers: dict = {}
        if self._config.headers and isinstance(self._config.headers, dict):
            headers.update(self._config.headers)
        if ctx.headers and isinstance(ctx.headers, dict):
            headers.update(ctx.headers)
        if ctx.ua:
            headers.setdefault("User-Agent", ctx.ua)
        headers.update(extra)
        return headers

    def _check_json_response(self, res, ctx: SiteSigninContext) -> SigninResult:
        try:
            data = JsonUtils.loads(res.text)
        except Exception:
            return SigninResult.fail(ctx.site, "解析 JSON 响应失败")

        actual = data.get(self._config.json_success_path)
        if actual == self._config.json_success_value:
            return SigninResult.success(ctx.site)

        text = res.text
        for marker in self._config.success_markers:
            if marker in text:
                return SigninResult.success(ctx.site)
        for marker in self._config.already_markers:
            if marker in text:
                return SigninResult.already(ctx.site)

        return SigninResult.fail(ctx.site, f"接口返回 {res.text[:200]}")

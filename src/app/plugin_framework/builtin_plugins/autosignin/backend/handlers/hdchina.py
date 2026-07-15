import re

from app.infrastructure.http.auth import CookieAuth
from app.utils.json_utils import JsonUtils

from .base import SigninResult, SiteSigninContext, SiteSigninHandler


class HDChina(SiteSigninHandler):
    site_id = "hdchina"
    _ALREADY_REGEX = r'<a class="label label-default" href="#">已签到</a>'

    def signin(self, ctx: SiteSigninContext) -> SigninResult:
        site = ctx.site
        if not ctx.cookie:
            return SigninResult.fail(site, SigninResult.COOKIE_EXPIRED)

        cookie = self._filter_cookie(ctx.cookie)
        if "hdchina=" not in cookie:
            return SigninResult.fail(site, SigninResult.COOKIE_EXPIRED)

        base_headers = {"User-Agent": ctx.ua} if ctx.ua else {}

        with self._http_client(ctx) as client:
            try:
                index_res = client.get(
                    url="https://hdchina.org/index.php",
                    headers=base_headers,
                    auth=CookieAuth(cookie),
                )
            except Exception as e:
                self._plugin_ctx.warn(f"{site} 首页请求失败: {e}")
                return SigninResult.fail(site, SigninResult.SITE_UNREACHABLE)

        text = index_res.text
        if "login.php" in text or "阻断页面" in text:
            return SigninResult.fail(site, SigninResult.COOKIE_EXPIRED)

        if re.search(self._ALREADY_REGEX, text):
            return SigninResult.already(site)

        x_csrf = self._extract_csrf(text)
        if not x_csrf:
            return SigninResult.fail(site, "获取 x-csrf 失败")

        self._plugin_ctx.debug(f"{site} 获取到 x-csrf {x_csrf}")

        new_cookie = self._cookies_to_string(dict(index_res.cookies))
        sign_cookie = new_cookie or cookie

        with self._http_client(ctx) as client:
            try:
                sign_res = client.post(
                    url="https://hdchina.org/plugin_sign-in.php?cmd=signin",
                    data={"csrf": x_csrf},
                    headers=base_headers,
                    auth=CookieAuth(sign_cookie),
                )
            except Exception as e:
                self._plugin_ctx.warn(f"{site} 签到请求失败: {e}")
                return SigninResult.fail(site, SigninResult.REQUEST_FAILED)

        try:
            data = JsonUtils.loads(sign_res.text)
        except Exception:
            return SigninResult.fail(site, "解析 JSON 响应失败")

        if data.get("state"):
            return SigninResult.success(site)

        return SigninResult.fail(site, f"{data.get('msg', '未知错误')}")

    @staticmethod
    def _filter_cookie(cookie: str) -> str:
        parts = []
        for part in cookie.split(";"):
            if "hdchina=" in part:
                parts.append(part.strip())
        return "; ".join(parts)

    @staticmethod
    def _cookies_to_string(cookies: dict) -> str:
        return "; ".join(f"{k}={v}" for k, v in cookies.items())

    def _extract_csrf(self, text: str) -> str | None:
        m = re.search(r'<meta[^>]*name=["\']x-csrf["\'][^>]*content=["\']([^"\']+)["\']', text)
        if m:
            return m.group(1)
        return None

import re

from app.infrastructure.http.auth import CookieAuth
from app.infrastructure.http.client import HttpClientError
from app.plugin_framework.builtin_plugins.autosignin.backend.handlers.base import (
    SigninResult,
    SiteSigninContext,
    SiteSigninHandler,
)
from app.utils import StringUtils


class FreeFarm(SiteSigninHandler):
    site_id = "0ff"

    def signin(self, ctx: SiteSigninContext) -> SigninResult:
        site = ctx.site
        signurl = ctx.site_url
        cookie = ctx.cookie
        ua = ctx.ua
        base_url = StringUtils.get_base_url(signurl)
        attendance_url = base_url + "/attendance.php"
        client = self._http_client(ctx)

        if cookie:
            client._client.cookies.update(CookieAuth._parse_cookies(cookie))

        headers = {"User-Agent": str(ua) if ua else ""}
        if ctx.headers and isinstance(ctx.headers, dict):
            headers.update(ctx.headers)

        try:
            sign_res = client.get(url=attendance_url, headers=headers)
            text = sign_res.text
        except HttpClientError:
            return SigninResult.fail(site, SigninResult.SITE_UNREACHABLE)

        if self._is_login_page(text):
            return SigninResult.fail(site, SigninResult.COOKIE_EXPIRED)
        if "签到成功" in text:
            return SigninResult.success(site)

        pattern = r'src="([^"]*(?:slide_check|drag|slide\.)[^"]*\.js)"'
        match = re.search(pattern, text)
        if not match:
            return SigninResult.fail(site, f"签到接口返回 {text[:500]}")

        slide_url = f"{base_url}{match.group(1)}"
        slide_response = client.get(url=slide_url, headers=headers)

        pattern2 = r'"https://[^"]*set_access_token[^"]*"'
        match2 = re.search(pattern2, slide_response.text)
        if not match2:
            return SigninResult.fail(site, f"签到接口返回 {slide_response.text[:500]}")

        access_token_url = match2.group(0).strip('"')
        result_response = client.get(url=access_token_url, headers=headers)
        if result_response.status_code != 200:
            return SigninResult.fail(site, f"签到接口返回 HTTP {result_response.status_code}")

        access_response = client.get(url=attendance_url, headers=headers)
        if "签到成功" in access_response.text:
            return SigninResult.success(site)
        return SigninResult.fail(site, f"签到接口返回 {access_response.text[:500]}")

    @staticmethod
    def _is_login_page(html_text: str) -> bool:
        if "login.php" not in html_text:
            return False
        if 'type="password"' in html_text:
            return True
        if re.search(r'"login\.php', html_text):
            return True
        return False

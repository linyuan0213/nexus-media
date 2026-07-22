import re

from app.infrastructure.http.auth import CookieAuth
from app.utils import StringUtils

from .base import SigninResult, SiteSigninContext, SiteSigninHandler


class TTG(SiteSigninHandler):
    site_id = "ttg"
    _ALREADY_REGEX = r'<b style="color:green;">已签到</b>'
    _ALREADY_TEXT = "亲，您今天已签到过，不要太贪哦"
    _SUCCESS_TEXT = "您已连续签到"

    def signin(self, ctx: SiteSigninContext) -> SigninResult:
        site = ctx.site
        if not ctx.cookie:
            return SigninResult.fail(site, SigninResult.COOKIE_EXPIRED)

        base_url = StringUtils.get_base_url(ctx.site_url)
        base_headers = {"User-Agent": ctx.ua} if ctx.ua else {}

        with self._http_client(ctx) as client:
            try:
                index_res = client.get(
                    url=base_url,
                    headers=base_headers,
                    auth=CookieAuth(ctx.cookie),
                )
            except Exception as e:
                self._plugin_ctx.warn(f"{site} 首页请求失败: {e}")
                return SigninResult.fail(site, SigninResult.SITE_UNREACHABLE)

        text = index_res.text
        if "login.php" in text:
            return SigninResult.fail(site, SigninResult.COOKIE_EXPIRED)

        if re.search(self._ALREADY_REGEX, text):
            return SigninResult.already(site)

        signed_timestamp = self._extract(text, r'(?<=signed_timestamp: ")\d{10}')
        signed_token = self._extract(text, r'(?<=signed_token: ").*(?=")')
        if not signed_timestamp or not signed_token:
            return SigninResult.fail(site, "获取签名参数失败")

        self._plugin_ctx.debug(f"{site} signed_timestamp={signed_timestamp} signed_token={signed_token}")

        with self._http_client(ctx) as client:
            try:
                sign_res = client.post(
                    url=base_url + "/signed.php",
                    data={
                        "signed_timestamp": signed_timestamp,
                        "signed_token": signed_token,
                    },
                    headers=base_headers,
                    auth=CookieAuth(ctx.cookie),
                )
            except Exception as e:
                self._plugin_ctx.warn(f"{site} 签到请求失败: {e}")
                return SigninResult.fail(site, SigninResult.REQUEST_FAILED)

        sign_text = sign_res.text
        if self._SUCCESS_TEXT in sign_text:
            return SigninResult.success(site)
        if self._ALREADY_TEXT in sign_text:
            return SigninResult.already(site)

        return SigninResult.fail(site, "签到失败，未知原因")

    @staticmethod
    def _extract(text: str, pattern: str) -> str | None:
        m = re.search(pattern, text)
        return m.group(0) if m else None

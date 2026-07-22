import re

from app.infrastructure.http.auth import CookieAuth
from app.utils import StringUtils

from .base import SigninResult, SiteSigninContext, SiteSigninHandler


class HDUpt(SiteSigninHandler):
    site_id = "hdupt"
    _ALREADY_REGEX = ['<span id="yiqiandao">']

    def signin(self, ctx: SiteSigninContext) -> SigninResult:
        site = ctx.site
        cookie = ctx.cookie
        ua = ctx.ua
        base_url = StringUtils.get_base_url(ctx.site_url)

        client = self._http_client(ctx)
        try:
            index_res = client.get(
                url=base_url,
                headers={"User-Agent": ua} if ua else None,
                auth=CookieAuth(cookie) if cookie else None,
            )
        except Exception:
            return SigninResult.fail(site, SigninResult.SITE_UNREACHABLE)

        if cookie_result := self._check_cookie(index_res.text, site):
            return cookie_result
        if self.sign_in_result(html_res=index_res.text, regexs=self._ALREADY_REGEX):
            return SigninResult.already(site)

        try:
            sign_res = client.post(
                url=base_url + "/added.php?action=qiandao",
                headers={"User-Agent": ua} if ua else None,
                auth=CookieAuth(cookie) if cookie else None,
            )
        except Exception:
            return SigninResult.fail(site, SigninResult.REQUEST_FAILED)

        if re.findall(r"\d+", sign_res.text):
            return SigninResult.success(site)

        return SigninResult.fail(site, f"签到接口返回 {sign_res.text[:200]}")

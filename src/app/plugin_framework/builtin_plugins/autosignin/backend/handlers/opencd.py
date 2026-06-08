import json
import time
from typing import cast

from lxml import etree

from app.infrastructure.http.auth import CookieAuth
from app.infrastructure.http.client import HttpClientError
from app.infrastructure.ocr import OcrRecognizer
from app.plugin_framework.builtin_plugins.autosignin.backend.handlers.base import (
    SigninResult,
    SiteSigninContext,
    SiteSigninHandler,
)
from app.utils import StringUtils


class Opencd(SiteSigninHandler):
    site_url = "open.cd"

    def signin(self, ctx: SiteSigninContext) -> SigninResult:
        site = ctx.site
        signurl = ctx.site_url
        cookie = ctx.cookie
        ua = ctx.ua
        base_url = StringUtils.get_base_url(signurl)
        client = self._http_client(ctx)

        try:
            index_res = client.get(
                url=base_url,
                headers={"User-Agent": ua} if ua else None,
                auth=CookieAuth(cookie) if cookie else None,
                raise_for_status=False,
            )
        except HttpClientError:
            return SigninResult.fail(site, SigninResult.SITE_UNREACHABLE)

        if index_res.status_code != 200:
            return SigninResult.fail(site, SigninResult.SITE_UNREACHABLE)
        if cookie_result := self._check_cookie(index_res.text, site):
            return cookie_result
        if "/plugin_sign-in.php?cmd=show-log" in index_res.text:
            return SigninResult.already(site)

        try:
            sign_param_res = client.get(
                url=base_url + "/plugin_sign-in.php",
                headers={"User-Agent": ua} if ua else None,
                auth=CookieAuth(cookie) if cookie else None,
                raise_for_status=False,
            )
        except HttpClientError:
            return SigninResult.fail(site, SigninResult.SITE_UNREACHABLE)

        if sign_param_res.status_code != 200:
            return SigninResult.fail(site, SigninResult.SITE_UNREACHABLE)

        html = etree.HTML(sign_param_res.text)
        if not html:
            return SigninResult.fail(site, "签到失败")

        img_url = str(cast(list, html.xpath('//form[@id="frmSignin"]//img/@src'))[0] or "")
        img_hash = str(cast(list, html.xpath('//form[@id="frmSignin"]//input[@name="imagehash"]/@value'))[0] or "")
        if not img_url or not img_hash:
            return SigninResult.fail(site, "获取签到参数失败")

        img_get_url = base_url + "/" + img_url.lstrip("/")
        self._plugin_ctx.debug(f"获取到{site}验证码链接 {img_get_url}")

        times = 0
        ocr_result = None
        while times <= 3:
            ocr_result = OcrRecognizer().get_captcha_text(image_url=img_get_url, cookie=cookie, ua=ua)
            self._plugin_ctx.debug(f"ocr识别{site}验证码 {ocr_result}")
            if ocr_result and len(ocr_result) == 6:
                self._plugin_ctx.info(f"ocr识别{site}验证码成功 {ocr_result}")
                break
            times += 1
            self._plugin_ctx.debug(f"ocr识别{site}验证码失败，重试次数 {times}")
            time.sleep(1)

        if ocr_result:
            data = {"imagehash": img_hash, "imagestring": ocr_result}
            try:
                sign_res = client.post(
                    url=signurl,
                    data=data,
                    headers={"User-Agent": ua} if ua else None,
                    auth=CookieAuth(cookie) if cookie else None,
                    raise_for_status=False,
                )
            except HttpClientError:
                return SigninResult.fail(site, SigninResult.SITE_UNREACHABLE)

            if sign_res.status_code == 200:
                self._plugin_ctx.debug(f"sign_res返回 {sign_res.text}")
                sign_dict = json.loads(sign_res.text)
                if sign_dict["state"]:
                    return SigninResult.success(site)
                return SigninResult.fail(site, f"签到接口返回 {sign_dict}")

        return SigninResult.fail(site, "未获取到验证码")

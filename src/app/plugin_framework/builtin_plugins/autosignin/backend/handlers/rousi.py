import time

from app.infrastructure.cache_system.cookiecloud_adapter import CookiecloudAdapter
from app.infrastructure.http.auth import BearerAuth
from app.infrastructure.http.client import HttpClientError
from app.plugin_framework.builtin_plugins.autosignin.backend.handlers.base import (
    SigninResult,
    SiteSigninContext,
    SiteSigninHandler,
)
from app.utils.json_utils import JsonUtils


class Rousi(SiteSigninHandler):
    site_url = "rousi.pro"

    def _get_sign_token(self, site_info: dict) -> str | None:
        local_storage = CookiecloudAdapter().get_local_storage("rousi.pro")
        if local_storage:
            token = local_storage.get("token")
            if token:
                return token

        headers = site_info.get("headers")
        if headers:
            if isinstance(headers, str):
                try:
                    headers = JsonUtils.loads(headers)
                except Exception:
                    headers = None

            if isinstance(headers, dict):
                for key in headers:
                    if key.lower() in ["x-sign-token", "sign-authorization", "x-sign-authorization"]:
                        token = headers[key]
                        if token and token.startswith("Bearer "):
                            token = token[7:]
                        return token
                for key in headers:
                    if key.lower() == "authorization":
                        auth = headers[key]
                        if auth and auth.startswith("Bearer "):
                            return auth[7:]
                        elif auth:
                            return auth
        return None

    def signin(self, ctx: SiteSigninContext) -> SigninResult:
        site = ctx.site
        signurl = ctx.site_url
        ua = ctx.ua

        self._plugin_ctx.emit("site.local_storage_sync", {})
        time.sleep(10)

        token = self._get_sign_token(ctx.raw)
        if not token:
            return SigninResult.fail(site, "无法获取签到token，请检查LocalStorage或站点Headers配置")

        self._plugin_ctx.info(f"{site} 开始签到")
        client = self._http_client(ctx, timeout=30.0, auth=BearerAuth(token))

        res_text = None
        try:
            res = client.post(
                url=signurl,
                data='{"mode":"fixed"}',
                headers={
                    "accept": "application/json, text/plain, */*",
                    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,ja;q=0.7",
                    "content-type": "application/json",
                    "origin": "https://rousi.pro",
                    "referer": "https://rousi.pro/",
                    "User-Agent": ua,
                },
            )
            res_text = res.text
        except HttpClientError as e:
            if e.status_code is not None and e.response_text:
                res_text = e.response_text

        if res_text is None:
            return SigninResult.fail(site, "获取签到接口响应失败")

        try:
            res_json = JsonUtils.loads(res_text)
        except Exception as e:
            return SigninResult.fail(site, f"解析响应JSON失败: {str(e)}")

        if res_json.get("code") == 0:
            return SigninResult.success(site)
        if res_json.get("code") == 1:
            message = res_json.get("message", "")
            if "已签到" in message or "签到" in message:
                return SigninResult.already(site)
        return SigninResult.fail(site, f"信息：{res_json.get('message')}")

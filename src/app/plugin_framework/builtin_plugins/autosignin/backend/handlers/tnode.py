import re

from app.infrastructure.http.auth import CookieAuth
from app.plugin_framework.builtin_plugins.autosignin.backend.handlers.base import (
    SigninResult,
    SiteSigninContext,
    SiteSigninHandler,
)
from app.utils import StringUtils
from app.utils.json_utils import JsonUtils


class TnodeSigninHandler(SiteSigninHandler):
    site_id = "tnode"

    def signin(self, ctx: SiteSigninContext) -> SigninResult:
        site = ctx.site
        cookie = ctx.cookie
        ua = ctx.ua
        base_url = StringUtils.get_base_url(ctx.site_url)
        client = self._http_client(ctx)

        headers = {"User-Agent": ua} if ua else {}
        try:
            index_res = client.get(url=base_url, headers=headers, auth=CookieAuth(cookie) if cookie else None)
        except Exception:
            return SigninResult.fail(site, SigninResult.SITE_UNREACHABLE)

        if "login.php" in index_res.text:
            return SigninResult.fail(site, SigninResult.COOKIE_EXPIRED)

        csrf_match = re.search(r'<meta name="x-csrf-token" content="(.+?)">', index_res.text)
        if not csrf_match:
            return SigninResult.fail(site, "未获取到 CSRF Token")

        csrf_token = csrf_match.group(1)
        api_headers = {
            "x-csrf-token": csrf_token,
            "Content-Type": "application/json; charset=utf-8",
        }
        if ua:
            api_headers["User-Agent"] = ua

        try:
            skill_res = client.post(
                url=f"{base_url}/api/gaming/fireGenshinCharacterMagic",
                json={"all": 1, "resetModal": "true"},
                headers=api_headers,
                auth=CookieAuth(cookie) if cookie else None,
            )
        except Exception:
            return SigninResult.fail(site, "技能释放请求失败")

        if skill_res.status_code != 200:
            return SigninResult.fail(site, f"技能释放失败 HTTP {skill_res.status_code}")

        try:
            skill_data = JsonUtils.loads(skill_res.text)
        except Exception:
            return SigninResult.already(site)

        if skill_data.get("status") == 200:
            bonus = skill_data.get("data", {}).get("bonus", 0)
            return SigninResult.success(site) if bonus else SigninResult.already(site)

        return SigninResult.fail(site, f"技能释放返回 {skill_res.text[:200]}")

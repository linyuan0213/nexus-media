import time

from app.infrastructure.cache_system.cookiecloud_adapter import CookiecloudAdapter
from app.plugin_framework.builtin_plugins.autosignin.backend.handlers.base import (
    SigninResult,
    SiteSigninContext,
    SiteSigninHandler,
)
from app.utils.config_tools import get_ua
from app.infrastructure.chrome import ChromeClient


class MTeam(SiteSigninHandler):
    site_url = "kp.m-team.cc"

    def __init__(self, plugin_ctx, rate_limiter=None, drissionpage_helper=None):
        super().__init__(plugin_ctx, rate_limiter)
        self._drissionpage_helper = drissionpage_helper or ChromeClient()

    def signin(self, ctx: SiteSigninContext) -> SigninResult:
        site = ctx.site

        self._plugin_ctx.emit("site.local_storage_sync", {})
        time.sleep(10)
        local_storage = CookiecloudAdapter().get_local_storage("m-team.io")

        if not local_storage:
            return SigninResult.fail(site, "LocalStorage获取失败或为空")

        persist_user = local_storage.get("persist:user")
        auth = local_storage.get("auth")
        if not persist_user or not auth:
            return SigninResult.fail(site, "persist:user获取失败或为空")

        self._plugin_ctx.info(f"{site} 开始仿真登录")
        chrome = self._drissionpage_helper
        if ctx.is_chrome and chrome.get_status():
            self._plugin_ctx.info(f"{site} 开始仿真登录")
            html_text = chrome.get_page_html(
                url="https://kp.m-team.cc/index",
                local_storage=local_storage,
                user_agent=get_ua(),
                timeout=30,
            )
            if not html_text:
                return SigninResult.fail(site, "获取站点源码失败")
            if "魔力值" in html_text:
                return SigninResult.custom(True, f"[{site}]仿真登录成功")
            return SigninResult.fail(site, "未找到登录标识")

        return SigninResult.already(site)

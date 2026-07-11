import time

from app.infrastructure.cache_system.cookiecloud_adapter import CookiecloudAdapter
from app.infrastructure.chrome import BrowserSession
from app.plugin_framework.builtin_plugins.autosignin.backend.handlers.base import (
    SigninResult,
    SiteSigninContext,
    SiteSigninHandler,
)
from app.utils.browser_mode import get_chrome_server_url
from app.utils.config_tools import get_ua


class MTeam(SiteSigninHandler):
    site_url = "kp.m-team.cc"

    def __init__(self, plugin_ctx, rate_limiter=None):
        super().__init__(plugin_ctx, rate_limiter)

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
        if ctx.is_chrome:
            server_url = get_chrome_server_url()
            if not server_url:
                return SigninResult.fail(site, "Chrome 服务器未配置或未启用")
            try:
                with BrowserSession(
                    site_key=site,
                    server_url=server_url,
                    user_agent=get_ua(),
                ) as session:
                    session.navigate("about:blank")
                    js_items = ", ".join(
                        f"['{k.replace(chr(39), chr(92) + chr(39))}', '{v.replace(chr(39), chr(92) + chr(39))}']"
                        for k, v in local_storage.items()
                    )
                    session.execute(
                        "var items = [" + js_items + "]; items.forEach(function(item){"
                        "localStorage.setItem(item[0], item[1]); });"
                    )
                    result = session.navigate("https://kp.m-team.cc/index", timeout=90)
                    html_text = result.get("html", "")
            except Exception as e:
                self._plugin_ctx.warn(f"{site} 仿真登录失败: {e!s}")
                return SigninResult.fail(site, "获取站点源码失败")
            if not html_text:
                return SigninResult.fail(site, "获取站点源码失败")
            if "魔力值" in html_text:
                return SigninResult.custom(True, f"[{site}]仿真登录成功")
            return SigninResult.fail(site, "未找到登录标识")

        return SigninResult.already(site)

"""Piggo 日历签到处理器（SPA Token + 浏览器过 Cloudflare）."""

from __future__ import annotations

import json
import threading
import time
import uuid

from app.infrastructure.chrome import BrowserSession
from app.sites.credential_provider import resolve_spa_credentials
from app.utils.browser_mode import get_chrome_server_url

from .base import SigninResult, SiteSigninContext, SiteSigninHandler

_PIGGO_BROWSER_LOCK = threading.Lock()


class Piggo(SiteSigninHandler):
    site_id = "piggo"

    def signin(self, ctx: SiteSigninContext) -> SigninResult:
        site = ctx.site
        site_def = self._plugin_ctx.site_engine.get_by_id(ctx.site_id)
        spa = resolve_spa_credentials(site_def, ctx.raw)
        token = spa.bearer_token
        if not token:
            return SigninResult.fail(site, "SPA Token 未配置，请同步 CookieCloud 或填写站点 SPA Token")
        server_url = get_chrome_server_url()
        if not server_url:
            return SigninResult.fail(site, "Chrome 服务器未配置")
        try:
            with _PIGGO_BROWSER_LOCK:
                with BrowserSession(
                    site_key="piggo",
                    server_url=server_url,
                    cookie=spa.cookie or ctx.cookie,
                    cleanup_auto_tabs=True,
                    slot_timeout=180.0,
                ) as session:
                    tab = f"piggo_calendar_{uuid.uuid4().hex[:6]}"
                    session.navigate("https://piggo.me/", tab_name=tab)
                    session.execute("localStorage.setItem('pig_token', %s)" % json.dumps(token))
                    session.navigate("https://piggo.me/calendar", tab_name=tab)
                    time.sleep(3)
                    # idle lock 只需浏览器会话确认；若出现密码框则无法自动完成
                    if "/locked" in str(session.current_page().get("url") or ""):
                        session.execute(
                            "(()=>{const b=[...document.querySelectorAll('button')]"
                            ".find(x=>x.innerText.trim()==='解锁');if(b)b.click()})()"
                        )
                        time.sleep(3)
                        session.navigate("https://piggo.me/calendar", tab_name=tab)
                        time.sleep(2)
                    text = str(session.execute("return document.body.innerText||''") or "")
                    if "已签到" in text:
                        return SigninResult.already(site)
                    clicked = session.execute(
                        "(()=>{const b=document.querySelector('button.cal-att-pill.act')"
                        "||[...document.querySelectorAll('button')]"
                        ".find(x=>x.innerText.trim().startsWith('签到'));"
                        "if(!b)return '';b.click();return b.innerText.trim();})()"
                    )
                    if not clicked:
                        return SigninResult.fail(site, "未找到日历签到按钮")
                    time.sleep(5)
                    text = str(session.execute("return document.body.innerText||''") or "")
                    if any(x in text for x in ("签到成功", "补签成功", "已签到")):
                        return SigninResult.success(site)
                    return SigninResult.fail(site, f"签到后未确认: {text[:200]}")
        except Exception as exc:
            return SigninResult.fail(site, f"浏览器签到异常: {exc}")

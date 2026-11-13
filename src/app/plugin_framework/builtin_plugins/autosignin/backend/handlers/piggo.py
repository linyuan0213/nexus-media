"""Piggo 日历签到处理器（SPA Token + 浏览器过 Cloudflare）."""

from __future__ import annotations

import json
import threading
import time
import uuid

from app.infrastructure.chrome import BrowserSession
from app.sites.config.credential_provider import SpaCredentials, resolve_spa_credentials
from app.utils.browser_mode import get_chrome_server_url

from .base import SigninResult, SiteSigninContext, SiteSigninHandler

_PIGGO_BROWSER_LOCK = threading.Lock()


class Piggo(SiteSigninHandler):
    site_id = "piggo"

    @staticmethod
    def _browser_user(spa: SpaCredentials) -> dict | None:
        user = spa.local_storage.get("pig_user")
        if isinstance(user, str):
            try:
                user = json.loads(user)
            except (TypeError, ValueError):
                return None
        if not isinstance(user, dict) or not user.get("id"):
            return None
        return user

    @staticmethod
    def _wait_js(session: BrowserSession, script: str, timeout: float = 15.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if session.execute(script):
                return True
            time.sleep(0.5)
        return False

    def _restore_spa_session(
        self,
        session: BrowserSession,
        spa: SpaCredentials,
    ) -> SigninResult | None:
        """把 CookieCloud 的 token/user/visitor 注入 SPA，避免整页加载丢失登录态。

        Piggo 的 token 与 visitorId 绑定；SPA 整页启动会生成新的 visitor，
        导致 /boot、/calendar 401 并清空 token。这里在已加载的页面里恢复
        Pinia auth store，并统一改写 XHR 的 visitorId，再走客户端路由。
        """
        user = self._browser_user(spa)
        visitor = str(spa.visitor_id or spa.local_storage.get("pig_visitorid") or "").strip()
        if not user:
            return SigninResult.fail(self.site_id, "SPA 用户信息缺失，请重新同步 CookieCloud")
        if not visitor:
            return SigninResult.fail(self.site_id, "SPA visitorId 缺失，请重新同步 CookieCloud")

        token_json = json.dumps(spa.bearer_token)
        visitor_json = json.dumps(visitor)
        user_json = json.dumps(user, ensure_ascii=False)
        installed = session.execute(
            "return (() => {"
            f"const v = {visitor_json};"
            "if (window.__piggoVisitorPatched) { window.__piggoVisitorId = v; return true; }"
            "const H = XMLHttpRequest.prototype.setRequestHeader;"
            "XMLHttpRequest.prototype.setRequestHeader = function(k, val) {"
            "  if (String(k).toLowerCase() === 'visitorid') val = window.__piggoVisitorId || v;"
            "  return H.call(this, k, val);"
            "};"
            "window.__piggoVisitorId = v;"
            "window.__piggoVisitorPatched = true;"
            "return true;"
            "})()"
        )
        if not installed:
            return SigninResult.fail(self.site_id, "浏览器 SPA 页面未就绪")

        restored = session.execute(
            "return (() => {"
            "try {"
            "  const app = document.querySelector('#app').__vue_app__;"
            "  const g = app.config.globalProperties;"
            "  const store = g.$pinia._s.get('auth');"
            f"  localStorage.setItem('pig_token', {token_json});"
            f"  localStorage.setItem('pig_user', JSON.stringify({user_json}));"
            f"  window.__ptvisitorid = {visitor_json};"
            f"  store.setSession({token_json}, {user_json});"
            "  return !!store.token;"
            "} catch (e) { return false; }"
            "})()"
        )
        if not restored:
            return SigninResult.fail(self.site_id, "SPA 登录态恢复失败")

        sign = session.execute(
            "return fetch('/v1/web/auth/sign', {"
            "  credentials: 'include',"
            "  headers: {"
            f"    Authorization: 'Bearer ' + {token_json},"
            f"    visitorId: {visitor_json},"
            "    ts: String(Math.floor(Date.now() / 1000)),"
            "    version: '1.0.0',"
            "    webversion: '1'"
            "  }"
            "}).then(r => r.json()).then(d => {"
            "  if (d.code !== 0 || !d.data || !d.data.sign) return false;"
            "  window.__ptSpaSign = d.data.sign;"
            "  return true;"
            "}).catch(() => false)"
        )
        if not sign:
            return SigninResult.fail(self.site_id, "SPA 登录态刷新失败")

        session.execute(
            "return (() => {"
            "try {"
            "  const g = document.querySelector('#app').__vue_app__.config.globalProperties;"
            "  if (g.$router.currentRoute.value.path !== '/calendar') g.$router.push('/calendar');"
            "  return true;"
            "} catch (e) { return false; }"
            "})()"
        )
        return None

    def signin(self, ctx: SiteSigninContext) -> SigninResult:
        site = ctx.site
        site_def = self._plugin_ctx.site_engine.get_by_id(ctx.site_id)
        spa = resolve_spa_credentials(site_def, ctx.raw)
        if not spa.bearer_token:
            return SigninResult.fail(site, "SPA Token 未配置，请同步 CookieCloud 或填写站点 SPA Token")
        server_url = get_chrome_server_url()
        if not server_url:
            return SigninResult.fail(site, "Chrome 服务器未配置")
        try:
            with _PIGGO_BROWSER_LOCK:
                with BrowserSession(
                    site_key="piggo",
                    server_url=server_url,
                    cleanup_auto_tabs=True,
                    slot_timeout=180.0,
                ) as session:
                    tab = f"piggo_calendar_{uuid.uuid4().hex[:6]}"
                    session.navigate(
                        "https://piggo.me/login",
                        tab_name=tab,
                        cookie=spa.cookie or ctx.cookie,
                    )
                    if not self._wait_js(
                        session,
                        "return !!document.querySelector('#app')?.__vue_app__",
                    ):
                        return SigninResult.fail(site, "SPA 页面加载超时")

                    failed = self._restore_spa_session(session, spa)
                    if failed:
                        return failed

                    if not self._wait_js(
                        session,
                        "return !!document.querySelector('button.cal-att-pill')",
                        timeout=15.0,
                    ):
                        text = str(session.execute("return document.body.innerText||''") or "")
                        if "/login" in str(session.current_page().get("url") or ""):
                            return SigninResult.fail(site, "SPA Token/Cookie 已失效，请重新登录猪猪并同步 CookieCloud")
                        return SigninResult.fail(site, f"日历加载失败: {text[:120]}")

                    text = str(session.execute("return document.body.innerText||''") or "")
                    if "已签到" in text or session.execute(
                        "return [...document.querySelectorAll('.cal-att-pill')]"
                        ".some(b => (b.innerText || '').includes('已签到'))"
                    ):
                        return SigninResult.already(site)

                    total_before = str(
                        session.execute(
                            "(()=>{const m=document.body.innerText.match(/累计签到(\\d+)天/);return m?m[1]:''})()"
                        )
                        or ""
                    )
                    clicked = session.execute(
                        "(()=>{const b=document.querySelector('button.cal-att-pill.act')"
                        "||[...document.querySelectorAll('button')]"
                        ".find(x=>x.innerText.trim().startsWith('签到'));"
                        "if(!b)return '';b.click();return b.innerText.trim();})()"
                    )
                    if not clicked:
                        if "累计签到" in text:
                            return SigninResult.already(site)
                        return SigninResult.fail(site, "未找到日历签到按钮")

                    # 点击后才会出现站点人机验证；nexus-chrome 负责点选并等待 token。
                    time.sleep(2)
                    try:
                        solved = session.turnstile(90)
                    except Exception:  # noqa: BLE001 - 无验证码时签到可能已完成
                        solved = {}
                    time.sleep(6)
                    text = str(session.execute("return document.body.innerText||''") or "")
                    signed = session.execute(
                        "return [...document.querySelectorAll('.cal-att-pill')]"
                        ".some(b => (b.innerText || '').includes('已签到'))"
                    )
                    total_after = str(
                        session.execute(
                            "(()=>{const m=document.body.innerText.match(/累计签到(\\d+)天/);return m?m[1]:''})()"
                        )
                        or ""
                    )
                    if (
                        "签到成功" in text
                        or "补签成功" in text
                        or "已签到" in text
                        or signed
                        or (total_before and total_after and total_after != total_before)
                    ):
                        return SigninResult.success(site)
                    if not solved.get("solved"):
                        return SigninResult.fail(site, "Cloudflare Turnstile 未通过")
                    return SigninResult.fail(site, f"签到后未确认: {text[:200]}")
        except Exception as exc:
            return SigninResult.fail(site, f"浏览器签到异常: {exc}")

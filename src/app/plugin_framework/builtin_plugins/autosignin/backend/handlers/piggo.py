"""Piggo 日历签到处理器（SPA Token + 浏览器过 Cloudflare）."""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime
from urllib.parse import urlencode

from app.infrastructure.chrome import BrowserSession
from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.sites.config.credential_provider import SpaCredentials, resolve_spa_credentials
from app.sites.config.runtime_config import SiteRuntimeConfig
from app.sites.http import auth_headers, spa_signer
from app.utils.browser_mode import browser_site_key, get_chrome_server_url

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
            except TypeError, ValueError:
                return None
        if not isinstance(user, dict) or not user.get("id"):
            return None
        return user

    @staticmethod
    def _preload_turnstile(session: BrowserSession) -> None:
        """业务页的 Turnstile 动态脚本可能未加载，提前注入确保验证码组件可渲染."""
        session.execute(
            "return (() => {"
            "if (window.turnstile) return true;"
            "const s = document.createElement('script');"
            "s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';"
            "s.async = true;"
            "s.defer = true;"
            "document.head.appendChild(s);"
            "return true;"
            "})()"
        )
        for _ in range(20):
            if session.execute("return typeof window.turnstile === 'object'"):
                return
            time.sleep(0.5)

    @staticmethod
    def _dismiss_tour(session: BrowserSession) -> None:
        """关闭站点的首次使用引导/浮层，避免遮挡签到按钮."""
        session.execute(
            "return (() => {"
            "let n = 0;"
            "for (const el of document.querySelectorAll('button,a')) {"
            "  const text = String(el.innerText || '').trim();"
            "  if (text === '跳过' || text === '关闭') { el.click(); n += 1; }"
            "}"
            "return n;"
            "})()"
        )

    def _calendar_checked(self, ctx: SiteSigninContext, spa: SpaCredentials) -> bool | None:
        """从站点日历接口读取今日真实签到状态；无法判断时返回 None."""
        try:
            site_def = self._plugin_ctx.site_engine.get_by_id(ctx.site_id)
            if site_def is None:
                return None
            runtime = SiteRuntimeConfig.resolve(site_def, ctx.raw, "search")
            user_config = dict(runtime.user_config)
            user_config.update(
                {
                    "bearer_token": spa.bearer_token,
                    "visitor_id": spa.visitor_id,
                    "cookie": spa.cookie,
                }
            )
            headers, auth = auth_headers.build_auth(
                self._plugin_ctx.site_engine, site_def, user_config, api=runtime.api
            )
            headers["Cookie"] = spa.cookie
            client = HttpClient(config=HttpClientConfig(proxy_url=ctx.proxy_url))
            now = datetime.now()
            url = (
                f"{runtime.api.base_url.rstrip('/')}/v1/web/calendar?"
                f"{urlencode({'year': now.year, 'month': now.month})}"
            )
            headers = spa_signer.spa_signed_headers(
                self._plugin_ctx.site_engine,
                runtime.api,
                user_config,
                client,
                headers,
                "GET",
                url,
                auth=auth,
            )
            res = client.get(url, headers=headers, auth=auth, timeout=30)
            payload = res.json()
            if payload.get("code") != 0:
                return None
            today = now.strftime("%Y-%m-%d")
            cells = (payload.get("data") or {}).get("cells") or []
            cell = next((item for item in cells if item.get("ymd") == today), None)
            return bool(cell and cell.get("checked"))
        except Exception:
            return None

    @staticmethod
    def _is_signed_pill(text: str) -> bool:
        """只把签到按钮本身的“已签到”视为已完成，避免正文/历史记录误报."""
        return "".join(str(text or "").split()) == "已签到"

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
        if not visitor:
            # CookieCloud 可能只同步 token/user，visitorId 由 SPA 首次启动生成。
            visitor = str(
                session.execute(
                    "return localStorage.getItem('pig_visitorid')"
                    " || localStorage.getItem('visitorId')"
                    " || window.__ptvisitorid || ''"
                )
                or ""
            ).strip()
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
            f"  localStorage.setItem('pig_visitorid', {visitor_json});"
            f"  localStorage.setItem('visitorId', {visitor_json});"
            f"  window.__ptvisitorid = {visitor_json};"
            f"  store.setSession({token_json}, {user_json});"
            "  return !!store.token;"
            "} catch (e) { return false; }"
            "})()"
        )
        if not restored:
            return SigninResult.fail(self.site_id, "SPA 登录态恢复失败")

        restored_session = session.execute(
            "return (async () => {"
            "try {"
            "  const g = document.querySelector('#app').__vue_app__.config.globalProperties;"
            "  const store = g.$pinia._s.get('auth');"
            "  for (let i = 0; i < 3; i += 1) {"
            "    try {"
            f"      store.setSession({token_json}, {user_json});"
            "      store.booted = false;"
            "      await store.boot();"
            "      if (store.token && store.booted) return true;"
            "    } catch (e) {}"
            "    await new Promise(r => setTimeout(r, 800));"
            "  }"
            "  return false;"
            "} catch (e) { return false; }"
            "})()"
        )
        if not restored_session:
            return SigninResult.fail(self.site_id, "SPA 登录态刷新失败")

        route = ""
        for _ in range(3):
            route = session.execute(
                "return (async () => {"
                "try {"
                "  const g = document.querySelector('#app').__vue_app__.config.globalProperties;"
                "  await g.$router.push('/calendar');"
                "  return g.$router.currentRoute.value.path;"
                "} catch (e) { return ''; }"
                "})()"
            )
            if route == "/calendar":
                break
            time.sleep(1)
        if route != "/calendar":
            return SigninResult.fail(self.site_id, "日历页面加载失败")
        return None

    def signin(self, ctx: SiteSigninContext) -> SigninResult:
        site = ctx.site
        site_def = self._plugin_ctx.site_engine.get_by_id(ctx.site_id)
        spa = resolve_spa_credentials(site_def, ctx.raw)
        if not spa.bearer_token:
            return SigninResult.fail(site, "SPA Token 未配置，请同步 CookieCloud 或填写站点 SPA Token")
        checked = self._calendar_checked(ctx, spa)
        if checked is True:
            return SigninResult.already(site)
        server_url = get_chrome_server_url()
        if not server_url:
            return SigninResult.fail(site, "Chrome 服务器未配置")
        try:
            with _PIGGO_BROWSER_LOCK:
                with BrowserSession(
                    site_key=browser_site_key(ctx.raw, ctx.site_url),
                    server_url=server_url,
                    cleanup_auto_tabs=True,
                    slot_timeout=180.0,
                ) as session:
                    tab = f"auto_piggo_calendar_{uuid.uuid4().hex[:6]}"
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
                    self._dismiss_tour(session)

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
                    # 页面正文/日历记录里也可能出现“已签到”，必须只看签到按钮本身。
                    pill_texts = session.execute(
                        "return JSON.stringify("
                        "[...document.querySelectorAll('button.cal-att-pill')]"
                        ".map(b => b.innerText || ''))"
                    )
                    try:
                        pills = json.loads(pill_texts or "[]")
                    except TypeError, ValueError:
                        pills = []
                    pill_signed = any(self._is_signed_pill(t) for t in pills)
                    if pill_signed:
                        return SigninResult.already(site)

                    self._dismiss_tour(session)
                    total_before = str(
                        session.execute(
                            "(()=>{const m=document.body.innerText.match(/累计签到(\\d+)天/);return m?m[1]:''})()"
                        )
                        or ""
                    )
                    clicked = session.execute(
                        "return (()=>{const b=document.querySelector('button.cal-att-pill.act')"
                        "||[...document.querySelectorAll('button')]"
                        ".find(x=>x.innerText.trim().startsWith('签到'));"
                        "if(!b)return '';b.click();return b.innerText.trim();})()"
                    )
                    if not clicked:
                        if pill_signed:
                            return SigninResult.already(site)
                        return SigninResult.fail(site, "未找到日历签到按钮")

                    # 点击后才会出现站点人机验证；先等内嵌组件挂载，再交给 nexus-chrome。
                    for _ in range(20):
                        if session.execute(
                            'return !!document.querySelector(".site-cap-root, .ts-box, '
                            "input[name='cf-turnstile-response']\")"
                        ):
                            break
                        time.sleep(0.5)
                    self._dismiss_tour(session)
                    try:
                        solved = session.turnstile(90)
                    except Exception:  # noqa: BLE001 - 无验证码时签到可能已完成
                        solved = {}
                    time.sleep(6)
                    text = str(session.execute("return document.body.innerText||''") or "")
                    pill_texts = session.execute(
                        "return JSON.stringify("
                        "[...document.querySelectorAll('button.cal-att-pill')]"
                        ".map(b => b.innerText || ''))"
                    )
                    try:
                        pills = json.loads(pill_texts or "[]")
                    except TypeError, ValueError:
                        pills = []
                    signed = any(self._is_signed_pill(t) for t in pills)
                    total_after = str(
                        session.execute(
                            "(()=>{const m=document.body.innerText.match(/累计签到(\\d+)天/);return m?m[1]:''})()"
                        )
                        or ""
                    )
                    if (
                        "签到成功" in text
                        or "补签成功" in text
                        or signed
                        or (total_before and total_after and total_after != total_before)
                    ):
                        return SigninResult.success(site)
                    if not solved.get("solved"):
                        return SigninResult.fail(site, "Cloudflare Turnstile 未通过")
                    return SigninResult.fail(site, f"签到后未确认: {text[:200]}")
        except Exception as exc:
            return SigninResult.fail(site, f"浏览器签到异常: {exc}")

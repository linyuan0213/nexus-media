"""Piggo 日历签到处理器（SPA Token + 浏览器过 Cloudflare）."""

from __future__ import annotations

import datetime
import json
import threading
import time
import uuid

from app.infrastructure.chrome import BrowserSession
from app.sites.credential_provider import resolve_spa_credentials
from app.utils.browser_mode import get_chrome_server_url

from .base import SigninResult, SiteSigninContext, SiteSigninHandler

_PIGGO_BROWSER_LOCK = threading.Lock()

_PIGGO_CALENDAR_JS = r"""
(async (ymd) => {
  try {
    const token = localStorage.getItem('pig_token') || '';
    const baseHeaders = {
      'Accept': 'application/json',
      'Authorization': 'Bearer ' + token,
      'X-Requested-With': 'XMLHttpRequest',
      'version': '1.0.0',
      'webversion': '1',
      'visitorId': window.__ptvisitorid || ''
    };
    const signRes = await fetch('/v1/web/auth/sign', { headers: baseHeaders });
    const signText = await signRes.text();
    let signPayload = {};
    try { signPayload = JSON.parse(signText); } catch (e) {}
    const sign = (signPayload.data && signPayload.data.sign) || signPayload.sign || '';
    if (signRes.status !== 200 || !sign) {
      window.__piggo_calendar_result = JSON.stringify({
        ok: false, stage: 'sign', status: signRes.status, text: signText.slice(0, 500)
      });
      return;
    }
    const ts = String(Math.floor(Date.now() / 1000));
    const nonce = [...crypto.getRandomValues(new Uint8Array(16))]
      .map(x => x.toString(16).padStart(2, '0')).join('');
    const message = 'POST\nv1/web/calendar/attendance\n' + ts + '\n' + nonce;
    const key = await crypto.subtle.importKey(
      'raw', new TextEncoder().encode(sign),
      { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']
    );
    const signature = await crypto.subtle.sign(
      'HMAC', key, new TextEncoder().encode(message)
    );
    const hmac = [...new Uint8Array(signature)]
      .map(x => x.toString(16).padStart(2, '0')).join('');
    const headers = Object.assign({}, baseHeaders, {
      'Content-Type': 'application/json',
      'ts': ts,
      'X-Spa-Nonce': nonce,
      'X-Spa-Hmac': hmac
    });
    const res = await fetch('/v1/web/calendar/attendance', {
      method: 'POST', headers, body: JSON.stringify({ ymd })
    });
    const text = await res.text();
    window.__piggo_calendar_result = JSON.stringify({
      ok: res.status === 200, status: res.status, text: text.slice(0, 2000)
    });
  } catch (error) {
    window.__piggo_calendar_result = JSON.stringify({
      ok: false, stage: 'exception', error: String(error)
    });
  }
})(%s)
"""


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
        ymd = datetime.datetime.now().strftime("%Y-%m-%d")
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
                    time.sleep(1)
                    session.execute(_PIGGO_CALENDAR_JS % json.dumps(ymd))
                    result = ""
                    for _ in range(30):
                        time.sleep(0.5)
                        result = str(session.execute("return window.__piggo_calendar_result||''") or "")
                        if result:
                            break
        except Exception as exc:
            return SigninResult.fail(site, f"浏览器签到异常: {exc}")
        if not result:
            return SigninResult.fail(site, "签到请求超时")
        try:
            payload = json.loads(result)
        except (TypeError, ValueError):
            return SigninResult.fail(site, result[:200])
        if not payload.get("ok"):
            text = str(payload.get("text") or payload.get("error") or "")
            if payload.get("status") == 401 or "Unauthenticated" in text:
                return SigninResult.fail(site, "SPA Token 已失效，请更新 CookieCloud/SPA 凭据")
            return SigninResult.fail(site, f"签到失败: {text[:200]}")
        try:
            body = json.loads(str(payload.get("text") or "{}"))
        except (TypeError, ValueError):
            return SigninResult.fail(site, "签到响应不是 JSON")
        data = body.get("data") or {}
        attendance = (data.get("detail") or {}).get("attendance") or {}
        status = str(attendance.get("status") or "")
        if status in {"checked", "today", "makeup"}:
            if status == "checked":
                return SigninResult.already(site)
            return SigninResult.success(site)
        return SigninResult.fail(site, f"签到未确认: {str(body)[:200]}")

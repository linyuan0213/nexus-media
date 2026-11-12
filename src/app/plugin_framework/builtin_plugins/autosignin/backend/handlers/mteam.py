import base64
import hashlib
import hmac
import re
import time
from typing import Any

from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.sites.config.credential_provider import resolve_spa_credentials
from app.utils.config_tools import get_ua
from app.utils.json_utils import JsonUtils

from .base import SigninResult, SiteSigninContext, SiteSigninHandler


class MTeam(SiteSigninHandler):
    """M-Team 签到处理器。

    通过调用 api.m-team.io 的 updateLastBrowse 接口完成签到/登录保号。
    请求需要：
    - localStorage.auth 中的 JWT Token
    - localStorage.did / visitorId / webversion
    - 从主站 JS 动态提取的 HMAC-SHA1 密钥
    """

    site_id = "mteam"
    _API_PATH = "/api/member/updateLastBrowse"
    _FALLBACK_SECRET = "HLkPcWmycL57mfJt"
    _DEFAULT_WEBVERSION = "2000"

    def __init__(self, plugin_ctx, rate_limiter=None):
        super().__init__(plugin_ctx, rate_limiter)

    def signin(self, ctx: SiteSigninContext) -> SigninResult:
        site = ctx.site
        site_def = self._plugin_ctx.site_engine.get_by_id(ctx.site_id)
        home_url = self._resolve_home_url(site_def)
        self._plugin_ctx.emit("site.local_storage_sync", {})
        time.sleep(10)

        spa = resolve_spa_credentials(site_def, ctx.raw)
        local_storage = spa.local_storage or {}
        if not local_storage:
            return SigninResult.fail(site, "LocalStorage 获取失败")

        jwt = spa.bearer_token or local_storage.get("auth")
        did = local_storage.get("did")
        visitor_id = spa.visitor_id or local_storage.get("visitorId")
        if not jwt:
            return SigninResult.fail(site, "localStorage auth 为空")
        # 设备指纹必须与浏览器一致：缺任一项会显著提高风控命中率（切勿空发）
        if not did or not visitor_id:
            return SigninResult.fail(site, "localStorage 缺少 did/visitorId，请在真实浏览器登录后同步 CookieCloud")
        # webversion 优先用浏览器同步值，缺失时回退当前站点前端版本（避免写死旧版本导致指纹不一致）
        webversion = local_storage.get("webversion") or self._DEFAULT_WEBVERSION

        home_url = self._resolve_home_url(site_def)
        secret = self._fetch_secret(home_url, site) or self._FALLBACK_SECRET

        timestamp_ms = int(time.time() * 1000)
        timestamp_s = timestamp_ms // 1000
        signature = self._build_sign("POST", self._API_PATH, timestamp_ms, secret)

        # 认证相关请求头：必填核心项（站点维护 headers 无法覆盖）
        headers: dict[str, str] = {
            "accept": "application/json, text/plain, */*",
            "authorization": jwt,
            "cache-control": "no-cache",
            "did": did,
            "dnt": "1",
            "origin": home_url,
            "pragma": "no-cache",
            "priority": "u=1, i",
            "referer": f"{home_url}/index",
            "ts": str(timestamp_s),
            "user-agent": ctx.ua or get_ua(),
            "visitorid": visitor_id,
            "webversion": webversion,
        }
        # 浏览器指纹类请求头（sec-ch-ua / accept-language / sec-fetch-* 等）取站点维护中维护的 headers
        maintained_headers = ctx.headers
        if isinstance(maintained_headers, str):
            try:
                maintained_headers = JsonUtils.loads(maintained_headers)
            except Exception:
                maintained_headers = {}
        if not isinstance(maintained_headers, dict):
            maintained_headers = {}
        core_keys = (
            "authorization",
            "did",
            "ts",
            "visitorid",
            "webversion",
            "origin",
            "referer",
            "user-agent",
            "content-type",
        )
        for hk, hv in maintained_headers.items():
            if hk and hv and hk.lower() not in core_keys:
                headers.setdefault(hk, hv)
        headers = {k: v for k, v in headers.items() if v}

        form = {
            "_timestamp": (None, str(timestamp_ms)),
            "_sgin": (None, signature),
        }

        api_base = self._resolve_api_base(site_def)
        url = f"{api_base}{self._API_PATH}"

        try:
            with HttpClient(
                config=HttpClientConfig(proxy_url=ctx.proxy_url),
                rate_limiter=self._rate_limiter,
            ) as client:
                res = client.post(url=url, files=form, headers=headers)
        except Exception as e:
            self._plugin_ctx.warn(f"{site} 签到请求失败: {e}")
            return SigninResult.fail(site, SigninResult.SITE_UNREACHABLE)

        return self._check_response(res, site)

    def _resolve_home_url(self, site_def: Any) -> str:
        domain = site_def.domain if site_def else "kp.m-team.cc"
        if not domain.startswith(("http://", "https://")):
            domain = f"https://{domain}"
        return domain.rstrip("/")

    def _resolve_api_base(self, site_def: Any) -> str:
        if site_def and site_def.api and site_def.api.base_url:
            return site_def.api.base_url.rstrip("/")
        return "https://api.m-team.cc"

    def _fetch_secret(self, home_url: str, site: str) -> str | None:
        try:
            headers = {
                "User-Agent": get_ua(),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            }
            with HttpClient(config=HttpClientConfig(default_headers=headers)) as client:
                home_res = client.get(url=f"{home_url}/index")
                main_match = re.search(r'src=["\']([^"\']*main\.(\w+)\.js)["\']', home_res.text)
                if not main_match:
                    return None
                js_url = main_match.group(1)
                if js_url.startswith("/"):
                    js_url = f"{home_url}{js_url}"
                js_res = client.get(url=js_url)
                m = re.search(r'\.join\(\[("[A-Za-z0-9]+"(?:,"[A-Za-z0-9]+")*)\],""\)', js_res.text)
                if not m:
                    return None
                chars = re.findall(r'"([A-Za-z0-9]+)"', m.group(1))
                secret = "".join(chars)
                if len(secret) >= 8:
                    self._plugin_ctx.debug(f"{site} 动态提取 M-Team 签名密钥成功")
                    return secret
        except Exception as e:
            self._plugin_ctx.warn(f"{site} 动态提取签名密钥失败: {e}")
        return None

    @staticmethod
    def _build_sign(method: str, path: str, timestamp_ms: int, secret: str) -> str:
        msg = f"{method}&{path}&{timestamp_ms}"
        sig = hmac.new(secret.encode(), msg.encode(), hashlib.sha1).digest()
        return base64.b64encode(sig).decode()

    def _check_response(self, res: Any, site: str) -> SigninResult:
        text = res.text
        try:
            data = JsonUtils.loads(text)
        except Exception:
            return SigninResult.fail(site, "解析 JSON 响应失败")

        code = data.get("code")
        message = str(data.get("message", ""))
        message_lower = message.lower()

        if data.get("success") is True or str(code) in ("0",):
            return SigninResult.success(site)
        # 2026-10 起 updateLastBrowse 成功返回 {"code":"1","message":"FAIL","data":null}
        if str(code) == "1" and message.upper() == "FAIL":
            return SigninResult.success(site)

        if str(code) == "401" or "full authentication" in message_lower:
            # 登录态(JWT)过期：切勿自动重新登录（密码/浏览器登录会触发站点风控）。
            # 提示用户在真实浏览器登录后同步 CookieCloud localStorage 即可静默续期
            return SigninResult.fail(site, "M-Team 登录态已过期，请在真实浏览器重新登录并同步 CookieCloud")
        # 风控：同一会话在其它环境/IP 被使用会触发“疑似登录凭证泄露”并吊销，需重新登录
        if any(k in message for k in ("泄露", "吊销", "異常", "异常登录")) or "revok" in message_lower:
            return SigninResult.fail(
                site, "M-Team 判定登录凭证异常并吊销会话，请在真实浏览器重新登录（勿与自动化并发）后同步 CookieCloud"
            )
        if "重复" in message or "already" in message_lower or "frequently" in message_lower:
            return SigninResult.already(site)

        return SigninResult.fail(site, f"接口返回 {text[:200]}")

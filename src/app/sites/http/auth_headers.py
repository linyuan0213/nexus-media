"""站点请求认证与动态 token（CSRF / Passkey）."""

import re
from typing import Any

import httpx2
from lxml import etree

import log
from app.infrastructure.http.auth import ApiKeyAuth, BearerAuth, CookieAuth
from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.sites.http.site_rate_limit import get_rate_limit_kwargs
from app.utils.config_tools import get_proxies
from app.utils.json_utils import JsonUtils


def build_auth(
    engine: Any,
    site: Any,
    user_config: dict,
    api: Any | None = None,
) -> tuple[dict, httpx2.Auth | None]:
    """构建全局认证（每个请求通用），返回 (headers, auth)。

    认证信息同时写入 headers（向后兼容）并返回 auth 对象（供 httpx 使用）。
    """
    headers = user_config.get("headers", {}) or {}
    if isinstance(headers, str):
        try:
            headers = JsonUtils.loads(headers)
        except Exception:
            headers = {}
    auth = None
    api = api if api is not None else getattr(site, "api", None)
    if not api:
        return headers, auth
    auth_type = api.auth.get("type", "")

    if auth_type == "api_key":
        hdr = api.auth.get("header_name", "x-api-key")
        token_key = str(api.auth.get("token_key") or "").strip()
        if token_key:
            key = user_config.get(token_key, "")
        else:
            key = user_config.get("api_key", "")
            # 向后兼容：旧配置可能把 api_key 放在 cookie 字段
            if not key:
                key = user_config.get("cookie", "")
        if key:
            headers[hdr] = key
            auth = ApiKeyAuth(key=hdr, value=key)
    elif auth_type == "bearer":
        token_key = str(api.auth.get("token_key") or "").strip()
        if token_key:
            token = user_config.get(token_key, "")
        else:
            token = user_config.get("bearer_token", "")
            # 向后兼容：旧配置可能把 bearer token 放在 cookie/api_key 字段
            if not token:
                token = user_config.get("api_key", "") or user_config.get("cookie", "")
        if token and not token.startswith("Bearer "):
            token = f"Bearer {token}"
        if token:
            headers["Authorization"] = token
            raw_token = token.removeprefix("Bearer ")
            auth = BearerAuth(raw_token)
    elif auth_type == "cookie":
        cookie = user_config.get("cookie", "")
        if cookie:
            auth = CookieAuth(cookie)
    elif auth_type == "csrf":
        hdr = api.auth.get("header_name", "X-CSRF-TOKEN")
        token = engine._resolve_auth_token(site, user_config, "csrf")
        if token:
            headers[hdr] = token
        cookie = user_config.get("cookie", "")
        if cookie:
            auth = CookieAuth(cookie)

    headers["Content-Type"] = headers.get("Content-Type", "application/json;charset=utf-8")
    ua_override = api.auth.get("user_agent") if api and api.auth else None
    if ua_override is not None:
        headers["User-Agent"] = ua_override
    elif user_config.get("ua"):
        headers["User-Agent"] = user_config.get("ua")
    return headers, auth


def build_headers(engine: Any, site: Any, user_config: dict, api: Any | None = None) -> dict:
    """返回包含认证信息的 headers 字典。"""
    headers, auth = build_auth(engine, site, user_config, api=api)
    if auth is not None and hasattr(auth, "_cookies"):
        cookie_dict = getattr(auth, "_cookies", {})
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookie_dict.items())
        if cookie_str:
            headers["Cookie"] = cookie_str
    return headers


def resolve_auth_token(engine: Any, site: Any, user_config: dict, token_type: str) -> str | None:
    cache_key = f"{site.id}:{token_type}"
    if cache_key in engine._auth_cache:
        return engine._auth_cache[cache_key]
    if token_type == "csrf":
        token = fetch_csrf_token(engine, site, user_config)
        log.debug(f"[SiteEngine]{site.name} CSRF token: {'OK' if token else 'FAIL'}")
    elif token_type == "passkey":
        token = fetch_passkey(engine, site, user_config)
    else:
        token = None
    if token:
        engine._auth_cache[cache_key] = token
    return token


def fetch_csrf_token(engine: Any, site: Any, user_config: dict) -> str | None:
    auth = site.api.auth
    csrf_url = auth.get("csrf_url", "").replace("{domain}", site.api.base_url.rstrip("/"))
    if not csrf_url:
        csrf_url = site.api.base_url.rstrip("/")
    cookie = user_config.get("cookie", "")
    ua = user_config.get("ua", "")
    proxy = get_proxies() if user_config.get("proxy") else None
    proxy_url = proxy.get("http") if proxy else None
    rate_limiter = getattr(engine, "site_limiter", None)
    rate_limiter_engine = rate_limiter.engine if rate_limiter else None
    rl_kwargs = get_rate_limit_kwargs(engine, site)
    try:
        res = HttpClient(
            config=HttpClientConfig(proxy_url=proxy_url),
            rate_limiter=rate_limiter_engine,
        ).get(url=csrf_url, headers={"User-Agent": ua}, auth=CookieAuth(cookie) if cookie else None, **rl_kwargs)
    except Exception as e:
        log.warn(f"[SiteEngine]{site.name} 获取CSRF失败: {e!r}")
        return None
    selector = auth.get("csrf_selector", "")
    selector_type = auth.get("csrf_selector_type", "regex")
    if selector_type == "regex":
        match = re.search(selector, res.text)
        return match.group(1) if match else None
    html_doc: Any = etree.HTML(res.text)
    els: Any = html_doc.xpath(selector)
    if els and hasattr(els[0], "text") and els[0].text:
        return els[0].text
    if els and hasattr(els[0], "attrs") and "content" in els[0].attrs:
        return els[0].attrs["content"]
    return None


def fetch_passkey(engine: Any, site: Any, user_config: dict) -> str | None:
    auth = site.api.auth
    url = auth.get("passkey_url", "")
    if not url:
        return None
    method = auth.get("passkey_method", "GET")
    response_key = auth.get("passkey_response_key", "data.passkey")
    base = site.api.base_url.rstrip("/")
    url = f"{base}{'/' if not url.startswith('/') else ''}{url}"
    headers = engine._build_headers(site, user_config)
    headers.pop("Content-Type", None)
    cookie = user_config.get("cookie", "")
    proxy = get_proxies() if user_config.get("proxy") else None
    proxy_url = proxy.get("http") if proxy else None
    rate_limiter = getattr(engine, "site_limiter", None)
    rate_limiter_engine = rate_limiter.engine if rate_limiter else None
    rl_kwargs = get_rate_limit_kwargs(engine, site)
    try:
        client = HttpClient(
            config=HttpClientConfig(proxy_url=proxy_url),
            rate_limiter=rate_limiter_engine,
        )
        if method.upper() == "GET":
            res = client.get(url=url, headers=headers, auth=CookieAuth(cookie) if cookie else None, **rl_kwargs)
        else:
            res = client.post(url=url, headers=headers, auth=CookieAuth(cookie) if cookie else None, **rl_kwargs)
        data = res.json()
        keys = response_key.split(".")
        val = data
        for k in keys:
            val = val.get(k) if isinstance(val, dict) else None
            if val is None:
                break
        return val
    except Exception:
        return None

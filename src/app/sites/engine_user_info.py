"""引擎用户信息 — 从 engine.py 拆分"""

import json

import log
from app.infrastructure.http.auth import CookieAuth
from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.sites.engine_tools import _get_rate_limit_kwargs
from app.utils.config_tools import get_proxies


def prefetch_user_profile(engine, url, site_cookie, site_headers=None, ua="", proxy=False, session=None):
    site_def = engine.get_by_url(url)
    if not site_def or not site_def.user_info:
        return None, None
    profile_cfg = site_def.user_info.get("profile")
    if not profile_cfg:
        return site_def, None
    try:
        base = site_def.api.base_url if site_def.api else url.rstrip("/")
        path = profile_cfg.get("path", "").lstrip("/")
        method = profile_cfg.get("method", "GET").upper()
        headers = engine._build_headers(
            site_def,
            {
                "cookie": site_cookie,
                "ua": ua,
                "proxy": proxy,
                "headers": site_headers,
            },
        )
        req_url = f"{base.rstrip('/')}/{path}" if path else base
        proxies = get_proxies() if proxy else None
        proxy_url = proxies.get("http") if proxies else None
        rate_limiter = getattr(engine, "site_limiter", None)
        rate_limiter_engine = rate_limiter.engine if rate_limiter else None
        rl_kwargs = _get_rate_limit_kwargs(engine, site_def)
        client = HttpClient(
            config=HttpClientConfig(proxy_url=proxy_url, timeout=30),
            rate_limiter=rate_limiter_engine,
        )
        if method == "POST":
            body = profile_cfg.get("body") or {}
            post_data = json.dumps(body)
            if not body or (isinstance(body, dict) and not body):
                post_data = None
                headers.pop("Content-Type", None)
            res = client.post(url=req_url, data=post_data, headers=headers, auth=CookieAuth(site_cookie), **rl_kwargs)
        else:
            params = profile_cfg.get("params") or None
            res = client.get(url=req_url, params=params, headers=headers, auth=CookieAuth(site_cookie), **rl_kwargs)
        parsed = res.json()
        log.warn(f"[prefetch]{site_def.name} status={res.status_code} keys={list(parsed.keys())[:5]}")
        if "data" in parsed and isinstance(parsed["data"], dict):
            log.warn(f"[prefetch]{site_def.name} data keys={list(parsed['data'].keys())[:10]}")
        return site_def, parsed
    except Exception:
        pass
    log.warn(f"[prefetch]{site_def.name if site_def else '?'} FAIL")
    return site_def, None

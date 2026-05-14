"""引擎用户信息 — 从 engine.py 拆分"""
import json

import log
from app.utils import RequestUtils
from app.utils.config_tools import get_proxies


def prefetch_user_profile(engine, url, site_cookie, site_headers=None,
                          ua="", proxy=False, session=None):
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
        headers = engine._build_headers(site_def, {
            "cookie": site_cookie, "ua": ua, "proxy": proxy,
            "headers": site_headers,
        })
        req_url = f"{base.rstrip('/')}/{path}" if path else base
        if method == "POST":
            body = profile_cfg.get("body") or {}
            post_data = json.dumps(body)
            if not body or (isinstance(body, dict) and not body):
                post_data = None
                headers.pop("Content-Type", None)
            res = RequestUtils(cookies=site_cookie, session=session, headers=headers,
                               proxies=get_proxies() if proxy else None,
                               timeout=30).post_res(url=req_url, data=post_data)
        else:
            params = profile_cfg.get("params") or None
            res = RequestUtils(cookies=site_cookie, session=session, headers=headers,
                               proxies=get_proxies() if proxy else None,
                               timeout=30).get_res(url=req_url, params=params)
        if res and res.status_code == 200:
            parsed = res.json()
            log.warn(f"【prefetch】{site_def.name} status={res.status_code} keys={list(parsed.keys())[:5]}")
            if 'data' in parsed and isinstance(parsed['data'], dict):
                log.warn(f"【prefetch】{site_def.name} data keys={list(parsed['data'].keys())[:10]}")
            return site_def, parsed
    except Exception:
        pass
    log.warn(f"【prefetch】{site_def.name if site_def else '?'} FAIL")
    return site_def, None

"""引擎下载链接解析 — 从 engine.py 拆分"""

from urllib.parse import quote

import log
from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.sites import engine_tools
from app.sites.engine_tools import _call_html_endpoint, _get_rate_limit_kwargs
from app.utils.config_tools import get_proxies


def _response_value(payload, key: str):
    """支持 data.url 这类点号路径，兼容旧的单层 key."""
    value = payload
    for part in str(key or "").split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def resolve_download_api(engine, url, site, user_config, tid, api=None):
    body = {}
    if site.download.body:
        for k, v in site.download.body.items():
            if isinstance(v, str):
                body[k] = v.format(tid=tid)
            else:
                body[k] = v
    headers, auth = engine._build_auth(site, user_config, api=api)
    headers.pop("Content-Type", None)
    proxy = get_proxies() if user_config.get("proxy") else None
    proxy_url = proxy.get("http") if proxy else None
    rate_limiter = getattr(engine, "site_limiter", None)
    rate_limiter_engine = rate_limiter.engine if rate_limiter else None
    rl_kwargs = _get_rate_limit_kwargs(engine, site)
    try:
        client = HttpClient(
            config=HttpClientConfig(
                proxy_url=proxy_url,
                enable_http2=bool(api and getattr(api, "http2", False)),
            ),
            rate_limiter=rate_limiter_engine,
        )
        headers = engine_tools.spa_signed_headers(
            engine, api, user_config, client, headers, site.download.method, url, auth=auth
        )
        if site.download.method == "POST":
            if api and (getattr(api, "auth", {}) or {}).get("spa"):
                headers["Content-Type"] = "application/json"
                res = client.post(url=url, json=body, headers=headers, auth=auth, **rl_kwargs)
            else:
                res = client.post(url=url, data=body, headers=headers, auth=auth, **rl_kwargs)
        else:
            res = client.get(url=url, headers=headers, auth=auth, **rl_kwargs)
        return _response_value(res.json(), site.download.response_key) or ""
    except Exception as exc:  # noqa: BLE001
        log.warn(f"[engine_download]下载链接解析失败: {type(exc).__name__}: {exc}")
        return None


def resolve_download_chained(engine, url, site, user_config, tid, api=None):
    headers, auth = engine._build_auth(site, user_config, api=api)
    headers.pop("Content-Type", None)
    proxy = get_proxies() if user_config.get("proxy") else None
    proxy_url = proxy.get("http") if proxy else None
    rate_limiter = getattr(engine, "site_limiter", None)
    rate_limiter_engine = rate_limiter.engine if rate_limiter else None
    rl_kwargs = _get_rate_limit_kwargs(engine, site)
    method = (getattr(site.download, "method", None) or "GET").upper()
    client = HttpClient(
        config=HttpClientConfig(
            proxy_url=proxy_url,
            enable_http2=bool(api and getattr(api, "http2", False)),
        ),
        rate_limiter=rate_limiter_engine,
    )
    try:
        headers = engine_tools.spa_signed_headers(engine, api, user_config, client, headers, method, url, auth=auth)
        if method == "POST":
            if api and (getattr(api, "auth", {}) or {}).get("spa"):
                headers["Content-Type"] = "application/json"
                res = client.post(url=url, json={}, headers=headers, auth=auth, **rl_kwargs)
            else:
                res = client.post(url=url, headers=headers, auth=auth, **rl_kwargs)
        else:
            res = client.get(url=url, headers=headers, auth=auth, **rl_kwargs)
        token = _response_value(res.json(), site.download.response_key) or ""
        if token and site.download.download_url and api:
            # token 可能含 +/= 等字符，作为查询参数必须 URL 编码
            encoded = quote(token, safe="")
            return site.download.download_url.format(base=api.base_url.rstrip("/"), token=encoded, tid=tid)
        return token
    except Exception as exc:  # noqa: BLE001
        log.warn(f"[engine_download]链式下载链接解析失败: {type(exc).__name__}: {exc}")
        return None


def resolve_html_download(engine, page_url, site, user_config):
    dl = site.download
    cfg = {"method": "GET", "path": "", "selectors": {}}
    if hasattr(dl, "selectors") and dl.selectors:
        cfg["selectors"] = dl.selectors
    elif isinstance(dl, dict) and dl.get("selectors"):
        cfg["selectors"] = dl["selectors"]
    result = _call_html_endpoint(engine, page_url, cfg, user_config, site=site)
    if result:
        return result.get("download") or result.get("enclosure")
    return None

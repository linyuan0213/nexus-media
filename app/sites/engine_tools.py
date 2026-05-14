"""引擎内部工具 — 从 engine.py 拆分"""
import json
import re

from lxml import etree

from app.utils import RequestUtils
from app.utils.config_tools import get_proxies


def _build_headers(engine, site, user_config):
    headers = user_config.get("headers", {}) or {}
    if isinstance(headers, str):
        try:
            headers = json.loads(headers)
        except Exception:
            headers = {}
    auth_type = site.api.auth.get("type", "") if site.api else ""

    if auth_type == "api_key":
        hdr = site.api.auth.get("header_name", "x-api-key")
        if hdr not in headers or not headers.get(hdr):
            key = user_config.get("cookie", "") or user_config.get("api_key", "")
            if key:
                headers[hdr] = key
    elif auth_type == "bearer":
        if "Authorization" not in headers or not headers.get("Authorization"):
            token = user_config.get("cookie", "") or user_config.get("api_key", "")
            if token and not token.startswith("Bearer "):
                token = f"Bearer {token}"
            if token:
                headers["Authorization"] = token
    elif auth_type == "cookie":
        cookie = user_config.get("cookie", "")
        if cookie:
            headers["Cookie"] = cookie
    elif auth_type == "csrf":
        hdr = site.api.auth.get("header_name", "X-CSRF-TOKEN")
        token = engine._resolve_auth_token(site, user_config, "csrf")
        if token:
            headers[hdr] = token

    headers["Content-Type"] = headers.get("Content-Type", "application/json;charset=utf-8")
    headers["User-Agent"] = user_config.get("ua", "")
    return headers


def _call_endpoint(engine, cfg, site, user_config, template_vars,
                   credential="", download_dir="", download=False):
    method = cfg.get("method", "GET")
    path = cfg.get("path", "").format(**template_vars)
    base = site.api.base_url.rstrip("/") if site.api else ""
    url = f"{base}{'/' if not path.startswith('/') else ''}{path}"

    headers = engine._build_headers(site, user_config)
    proxy = get_proxies() if user_config.get("proxy") else None

    if download:
        headers.pop("Content-Type", None)
        res = RequestUtils(headers=headers, proxies=proxy, timeout=30).get_res(url=url)
        if res and res.status_code == 200 and download_dir:
            import os
            fname = os.path.join(download_dir, f"{credential}.zip") if credential else "subtitle.zip"
            with open(fname, "wb") as f:
                f.write(res.content)
            return True
        return False

    if method == "POST":
        b = cfg.get("body") or {}
        body = {}
        for k, v in b.items():
            if isinstance(v, str):
                body[k] = v.format(**template_vars)
            elif isinstance(v, dict):
                body[k] = {sk: sv.format(**template_vars) if isinstance(sv, str) else sv for sk, sv in v.items()}
            else:
                body[k] = v
        post_data = json.dumps(body, separators=(',', ':')) if body else None
        res = RequestUtils(headers=headers, proxies=proxy, timeout=15).post_res(
            url=url, data=post_data)
    else:
        params = cfg.get("params")
        if params:
            params = {k: v.format(**template_vars) if isinstance(v, str) else v for k, v in params.items()}
        res = RequestUtils(headers=headers, proxies=proxy, timeout=15).get_res(url=url, params=params)

    if res and res.status_code == 200:
        try:
            return res.json()
        except Exception:
            return None
    return None


def _resolve_auth_token(engine, site, user_config, token_type):
    cache_key = f"{site.id}:{token_type}"
    if cache_key in engine._auth_cache:
        return engine._auth_cache[cache_key]
    auth = site.api.auth if site.api else {}
    if token_type == "csrf":
        token = _fetch_csrf_token(engine, site, user_config)
    elif token_type == "passkey":
        token = _fetch_passkey(engine, site, user_config)
    else:
        token = None
    if token:
        engine._auth_cache[cache_key] = token
    return token


def _fetch_csrf_token(engine, site, user_config):
    auth = site.api.auth
    csrf_url = auth.get("csrf_url", "").replace("{domain}", site.api.base_url.rstrip("/"))
    if not csrf_url:
        csrf_url = site.api.base_url.rstrip("/")
    cookie = user_config.get("cookie", "")
    ua = user_config.get("ua", "")
    proxy = get_proxies() if user_config.get("proxy") else None
    res = RequestUtils(headers={"User-Agent": ua}, cookies=cookie if cookie else None,
                       proxies=proxy, timeout=15).get_res(url=csrf_url)
    if not res or res.status_code != 200:
        return None
    selector = auth.get("csrf_selector", "")
    selector_type = auth.get("csrf_selector_type", "regex")
    if selector_type == "regex":
        match = re.search(selector, res.text)
        return match.group(1) if match else None
    html_doc = etree.HTML(res.text)
    els = html_doc.xpath(selector)
    if els and hasattr(els[0], 'text') and els[0].text:
        return els[0].text
    if els and hasattr(els[0], 'attrs') and 'content' in els[0].attrs:
        return els[0].attrs['content']
    return None


def _fetch_passkey(engine, site, user_config):
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
    if method.upper() == "GET":
        res = RequestUtils(headers=headers, cookies=cookie if cookie else None,
                           proxies=proxy, timeout=15).get_res(url=url)
    else:
        res = RequestUtils(headers=headers, cookies=cookie if cookie else None,
                           proxies=proxy, timeout=15).post_res(url=url)
    if res and res.status_code == 200:
        try:
            data = res.json()
        except Exception:
            return None
        keys = response_key.split(".")
        val = data
        for k in keys:
            val = val.get(k) if isinstance(val, dict) else None
            if val is None:
                break
        return val
    return None


def _call_html_endpoint(engine, url, html_cfg, user_config):
    method = html_cfg.get("method", "GET").upper()
    path = html_cfg.get("path", "")
    params = html_cfg.get("params") or {}
    body = html_cfg.get("body") or {}
    selectors = html_cfg.get("selectors") or {}

    domain = url.rstrip("/") if url else ""
    path_with_slash = f"/{path.lstrip('/')}" if path else ""
    req_url = f"{domain}{path_with_slash}"

    cookie = user_config.get("cookie", "")
    ua = user_config.get("ua", "")
    headers = {"User-Agent": ua} if ua else {}
    proxy = get_proxies() if user_config.get("proxy") else None

    if method == "POST":
        res = RequestUtils(headers=headers, cookies=cookie if cookie else None,
                           proxies=proxy, timeout=15).post_res(url=req_url, data=body)
    else:
        res = RequestUtils(headers=headers, cookies=cookie if cookie else None,
                           proxies=proxy, timeout=15).get_res(url=req_url, params=params)

    if not res or res.status_code != 200:
        return None

    html_doc = etree.HTML(res.text)
    result = {}
    for field_name, cfg in selectors.items():
        xpath = cfg.get("xpath", "")
        if not xpath:
            result[field_name] = cfg.get("default", "")
            continue
        try:
            els = html_doc.xpath(xpath)
        except Exception:
            els = []
        if not els:
            result[field_name] = cfg.get("default", "")
            continue
        attr = cfg.get("attribute", "")
        if attr and hasattr(els[0], 'attrib') and attr in els[0].attrib:
            result[field_name] = els[0].attrib[attr]
        elif hasattr(els[0], 'text'):
            result[field_name] = "".join(e for e in els[0].xpath('.//text()') if e).strip()
        elif isinstance(els[0], str):
            result[field_name] = els[0]
        else:
            result[field_name] = str(els[0])
    return result

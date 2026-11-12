"""站点 API / HTML 端点调用."""

import os
from typing import Any

from lxml import etree

import log
from app.infrastructure.http.auth import CookieAuth
from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.sites.http.site_rate_limit import get_rate_limit_kwargs
from app.utils.config_tools import get_proxies
from app.utils.json_utils import JsonUtils


def call_endpoint(
    engine: Any,
    cfg: dict,
    site: Any,
    user_config: dict,
    template_vars: dict,
    credential: str = "",
    download_dir: str = "",
    download: bool = False,
    api: Any | None = None,
) -> bool | list[dict] | None:
    method = cfg.get("method", "GET")
    path = cfg.get("path", "").format(**template_vars)
    api = api if api is not None else getattr(site, "api", None)
    base = api.base_url.rstrip("/") if api else ""
    url = f"{base}{'/' if not path.startswith('/') else ''}{path}"

    headers, auth = engine._build_auth(site, user_config, api=api)
    proxy = get_proxies() if user_config.get("proxy") else None
    proxy_url = proxy.get("http") if proxy else None

    rate_limiter = getattr(engine, "site_limiter", None)
    rate_limiter_engine = rate_limiter.engine if rate_limiter else None
    rl_kwargs = get_rate_limit_kwargs(engine, site)

    if download:
        headers.pop("Content-Type", None)
        try:
            res = HttpClient(
                config=HttpClientConfig(proxy_url=proxy_url),
                rate_limiter=rate_limiter_engine,
            ).get(url=url, headers=headers, auth=auth, **rl_kwargs)
            if download_dir:
                fname = os.path.join(download_dir, f"{credential}.zip") if credential else "subtitle.zip"
                with open(fname, "wb") as f:
                    f.write(res.content)
                return True
            return False
        except Exception:
            return False

    client = HttpClient(
        config=HttpClientConfig(proxy_url=proxy_url),
        rate_limiter=rate_limiter_engine,
    )
    try:
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
            # 始终发送 JSON 请求体（空 body 也发送 "{}"），部分站点对空 body 会返回“请求参数错误”
            post_data = JsonUtils.dumps(body, separators=(",", ":"))
            res = client.post(url=url, data=post_data, headers=headers, auth=auth, **rl_kwargs)
        else:
            params = cfg.get("params")
            if params:
                params = {k: v.format(**template_vars) if isinstance(v, str) else v for k, v in params.items()}
            headers.pop("Content-Type", None)
            res = client.get(url=url, params=params, headers=headers, auth=auth, **rl_kwargs)
        return res.json()
    except Exception as e:
        log.error(f"[SiteEngine]请求异常 {url}: {e}")
        return None


def call_html_endpoint(engine: Any, url: str, html_cfg: dict, user_config: dict, site: Any = None) -> dict | None:
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
    proxy_url = proxy.get("http") if proxy else None

    rate_limiter = getattr(engine, "site_limiter", None)
    rate_limiter_engine = rate_limiter.engine if rate_limiter else None
    rl_kwargs = get_rate_limit_kwargs(engine, site)

    try:
        client = HttpClient(
            config=HttpClientConfig(proxy_url=proxy_url),
            rate_limiter=rate_limiter_engine,
        )
        if method == "POST":
            res = client.post(
                url=req_url, data=body, headers=headers, auth=CookieAuth(cookie) if cookie else None, **rl_kwargs
            )
        else:
            res = client.get(
                url=req_url, params=params, headers=headers, auth=CookieAuth(cookie) if cookie else None, **rl_kwargs
            )
    except Exception:
        return None

    html_doc: Any = etree.HTML(res.text)
    result = {}
    for field_name, cfg in selectors.items():
        xpath = cfg.get("xpath", "")
        if not xpath:
            result[field_name] = cfg.get("default", "")
            continue
        try:
            els: Any = html_doc.xpath(xpath)
        except Exception:
            els = []
        if not els:
            result[field_name] = cfg.get("default", "")
            continue
        attr = cfg.get("attribute", "")
        if attr and hasattr(els[0], "attrib") and attr in els[0].attrib:
            result[field_name] = els[0].attrib[attr]
        elif hasattr(els[0], "text"):
            result[field_name] = "".join(e for e in els[0].xpath(".//text()") if e).strip()
        elif isinstance(els[0], str):
            result[field_name] = els[0]
        else:
            result[field_name] = str(els[0])
    return result

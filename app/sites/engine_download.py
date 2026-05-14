"""引擎下载链接解析 — 从 engine.py 拆分"""

from app.utils import RequestUtils
from app.utils.config_tools import get_proxies


def resolve_download_api(engine, url, site, user_config, tid):
    body = {}
    if site.download.body:
        for k, v in site.download.body.items():
            if isinstance(v, str):
                body[k] = v.format(tid=tid)
            else:
                body[k] = v
    headers = engine._build_headers(site, user_config)
    headers.pop("Content-Type", None)
    proxy = get_proxies() if user_config.get("proxy") else None
    if site.download.method == "POST":
        res = RequestUtils(headers=headers, proxies=proxy, timeout=15).post_res(
            url=url, data=body)
    else:
        res = RequestUtils(headers=headers, proxies=proxy, timeout=15).get_res(url=url)
    if res and res.status_code == 200:
        return res.json().get(site.download.response_key, "")
    return None


def resolve_download_chained(engine, url, site, user_config, tid):
    headers = engine._build_headers(site, user_config)
    headers.pop("Content-Type", None)
    proxy = get_proxies() if user_config.get("proxy") else None
    res = RequestUtils(headers=headers, proxies=proxy, timeout=15).get_res(url=url)
    if res and res.status_code == 200:
        token = res.json().get(site.download.response_key, "")
        if token and site.download.download_url and site.api:
            return site.download.download_url.format(
                base=site.api.base_url.rstrip("/"), token=token, tid=tid
            )
        return token
    return None


def resolve_html_download(engine, page_url, site, user_config):
    from app.sites.engine_tools import _call_html_endpoint
    dl = site.download
    cfg = {"method": "GET", "path": "", "selectors": {}}
    if hasattr(dl, 'selectors') and dl.selectors:
        cfg["selectors"] = dl.selectors
    elif isinstance(dl, dict) and dl.get("selectors"):
        cfg["selectors"] = dl["selectors"]
    result = _call_html_endpoint(engine, page_url, cfg, user_config)
    if result:
        return result.get("download") or result.get("enclosure")
    return None

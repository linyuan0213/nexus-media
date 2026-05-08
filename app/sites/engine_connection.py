# -*- coding: utf-8 -*-
"""引擎连接测试 — 从 engine.py 拆分"""
import time

from app.utils import RequestUtils
from app.utils.config_tools import get_proxies


def test_html_connection(engine, site, user_config):
    domain = site.domain.rstrip("/") if site.domain else ""
    if not domain.startswith("http"):
        domain = f"https://{domain}"
    start = time.time()
    cookie = user_config.get("cookie", "")
    ua = user_config.get("ua", "")
    headers = {"User-Agent": ua} if ua else {}
    proxy = get_proxies() if user_config.get("proxy") else None
    kwargs = {"headers": headers, "proxies": proxy, "timeout": 15}
    if cookie:
        kwargs["cookies"] = cookie
    res = RequestUtils(**kwargs).get_res(url=domain)
    latency = int((time.time() - start) * 1000)
    if not res:
        return False, "无法打开网站", latency
    if res.status_code != 200:
        return False, f"连接失败，状态码：{res.status_code}", latency
    from app.helper import SiteHelper
    if not SiteHelper.is_logged_in(res.text):
        return False, "Cookie失效", latency
    return True, "连接成功", latency

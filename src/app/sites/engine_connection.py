"""引擎连接测试 — 从 engine.py 拆分"""

import time

import log
from app.infrastructure.http.auth import CookieAuth
from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.sites import engine_tools
from app.sites.utils import is_logged_in
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
    proxy_url = proxy.get("http") if proxy else None
    latency = int((time.time() - start) * 1000)
    rate_limiter = getattr(engine, "site_limiter", None)
    rate_limiter_engine = rate_limiter.engine if rate_limiter else None
    rl_kwargs = engine_tools._get_rate_limit_kwargs(engine, site)
    try:
        res = HttpClient(
            config=HttpClientConfig(proxy_url=proxy_url, timeout=15, auth=CookieAuth(cookie) if cookie else None),
            rate_limiter=rate_limiter_engine,
        ).get(url=domain, headers=headers, **rl_kwargs)
    except Exception as e:
        log.error(f"[test_html_connection]请求异常 {domain}: {e}")
        return False, "无法打开网站", latency
    if not is_logged_in(res.text):
        return False, "Cookie失效", latency
    return True, "连接成功", latency

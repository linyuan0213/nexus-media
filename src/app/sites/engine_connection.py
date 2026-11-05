"""引擎连接测试 — 从 engine.py 拆分"""

import time

import log
from app.infrastructure.chrome.challenge import is_challenge
from app.infrastructure.http.auth import CookieAuth
from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.sites import engine_tools
from app.sites.utils import is_logged_in
from app.utils.browser_mode import build_browser_mode
from app.utils.config_tools import get_proxies


def test_html_connection(engine, site, user_config, base_url=None):
    # 优先使用调用方传入的实际站点地址（用户配置的签到域名/别名），回退站点规范域名
    domain = (base_url or site.domain or "").rstrip("/")
    if not domain.startswith("http"):
        domain = f"https://{domain}"
    if site.html and getattr(site.html, "test_connection", None):
        test_path = str(site.html.test_connection).lstrip("/")
        domain = f"{domain}/{test_path}"
    start = time.time()
    cookie = user_config.get("cookie", "")
    ua = user_config.get("ua", "")
    headers = {"User-Agent": ua} if ua else {}
    proxy = get_proxies() if user_config.get("proxy") else None
    proxy_url = proxy.get("http") if proxy else None
    rate_limiter = getattr(engine, "site_limiter", None)
    rate_limiter_engine = rate_limiter.engine if rate_limiter else None
    rl_kwargs = engine_tools._get_rate_limit_kwargs(engine, site)
    browser = (
        build_browser_mode(
            site_info=user_config,
            site_key=site.id,
            proxy_url=proxy_url,
            render_html=bool(user_config.get("browser_render")),
        )
        if user_config.get("chrome")
        else None
    )

    def _request(with_browser):
        client = None
        try:
            client = HttpClient(
                config=HttpClientConfig(
                    proxy_url=proxy_url,
                    auth=CookieAuth(cookie) if cookie else None,
                    browser=with_browser,
                ),
                rate_limiter=rate_limiter_engine,
            )
            return client.get(url=domain, headers=headers, **rl_kwargs)
        finally:
            if client is not None and with_browser is not None:
                client.close()

    res = None
    try:
        res = _request(None)
        if browser and (res is None or res.status_code != 200 or is_challenge(res.text or "")):
            res = _request(browser)
    except Exception as e:  # noqa: BLE001
        if browser:
            try:
                res = _request(browser)
            except Exception as browser_error:  # noqa: BLE001
                log.error(f"[SiteEngine]浏览器请求异常 {domain}: {browser_error}")
        else:
            log.error(f"[SiteEngine]请求异常 {domain}: {e}")
    latency = round(time.time() - start, 3)
    if res is None:
        return False, "无法打开网站", latency
    if res.status_code != 200:
        return False, f"连接失败，状态码：{res.status_code}", latency
    if not is_logged_in(res.text):
        return False, "Cookie失效", latency
    return True, "连接成功", latency

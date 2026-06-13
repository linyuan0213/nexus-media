from typing import cast
from urllib.parse import urlencode

from lxml import etree

from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.plugin_framework.builtin_plugins.autogenrss.backend._autogenrss._base import _ISiteRssGenHandler
from app.utils.config_tools import get_proxies
from app.utils.string_utils import StringUtils


class Ourbits(_ISiteRssGenHandler):
    """
    ourbits
    """

    site_url = "ourbits.club"

    @classmethod
    def match(cls, url):
        return bool(StringUtils.url_equal(url, cls.site_url))

    def gen_rss(self, site_info: dict):
        site = site_info.get("name")
        site_cookie = site_info.get("cookie")
        ua = site_info.get("ua")
        proxy = get_proxies() if site_info.get("proxy") else None

        proxy_url = proxy.get("http") if proxy else None
        engine = self._site_engine
        rate_limiter = getattr(engine, "site_limiter", None)
        rate_limiter_engine = rate_limiter.engine if rate_limiter else None
        try:
            html_res = HttpClient(
                config=HttpClientConfig(proxy_url=proxy_url),
                rate_limiter=rate_limiter_engine,
            ).get(url="https://ourbits.club/getrss.php", headers={"User-Agent": ua}, cookies=site_cookie)
            html_text = html_res.text
        except Exception:
            self.error("生成RSS失败，请检查站点连通性")
            return False, f"[{site}]生成RSS失败，请检查站点连通性"

        if "login.php" in html_text:
            self.error("生成RSS失败，cookie失效")
            return False, f"[{site}]生成RSS失败，cookie失效"
        passkey = self._get_passkey(html_text)
        params = [
            {"name": "inclbookmarked", "value": "0"},
            {"name": "https", "value": "1"},
            {"name": "icat", "value": "1"},
            {"name": "ismalldescr", "value": "1"},
            {"name": "isize", "value": "1"},
            {"name": "rows", "value": "50"},
            {"name": "search_mode", "value": "1"},
            {"name": "passkey", "value": passkey},
        ]

        rss_link = self._gen_link("https://ourbits.club/", params)
        self.debug(f"生成的rss: {rss_link}")

        if rss_link:
            self._site_repo.update_site_rssurl(site_info.get("id"), rss_link)
            self.info("生成RSS成功")
            return True, f"[{site}]生成RSS成功"
        else:
            self.info("生成RSS失败")
            return True, f"[{site}]生成RSS失败"

    @staticmethod
    def _get_passkey(html_text: str) -> str:
        if not html_text:
            return ""

        html = etree.HTML(html_text)
        return next((href for href in cast(list, html.xpath('//input[@name="passkey"]/@value'))), "")

    @staticmethod
    def _gen_link(site_url, params: list) -> str:
        if not params:
            return ""

        url_prefix = f"{site_url}/torrentrss.php?"
        query_params = [(item["name"], item["value"]) for item in params]
        query_str = urlencode(query_params)

        return f"{url_prefix}{query_str}"

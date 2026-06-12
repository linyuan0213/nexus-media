import json
from typing import cast

from lxml import etree

from app.plugin_framework.builtin_plugins.autogenrss.backend._autogenrss._base import _ISiteRssGenHandler
from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.utils.config_tools import get_proxies
from app.utils.json_utils import JsonUtils
from app.utils.string_utils import StringUtils


class HDHome(_ISiteRssGenHandler):
    """
    HDHome
    """

    site_url = "hdhome.org"

    @classmethod
    def match(cls, url):
        return bool(StringUtils.url_equal(url, cls.site_url))

    def gen_rss(self, site_info: dict):
        if not site_info:
            return ""
        site = site_info.get("name")
        site_url = site_info.get("signurl")
        site_cookie = site_info.get("cookie")
        ua = site_info.get("ua")
        headers = site_info.get("headers")
        if (not site_url or not site_cookie) and not headers:
            self.warn(f"未配置 {site!s} 的Cookie或请求头，无法获取到RSS")
            return ""
        if JsonUtils.is_valid_json(headers):
            headers = json.loads(headers or "{}")
        else:
            headers = {}

        home_url = StringUtils.get_base_url(site_url)
        rss_url = f"{home_url}/getrss.php"
        self.info(f"开始生成RSS站点：{site}")
        data = {
            "inclbookmarked": "0",
            "itemcategory": "1",
            "itemsmalldescr": "1",
            "itemsize": "1",
            "showrows": "50",
            "search": "",
            "search_mode": "1",
            "exp": "180",
        }

        headers.update({"User-Agent": ua})
        proxy = get_proxies() if site_info.get("proxy") else None
        proxy_url = proxy.get("http") if proxy else None
        engine = self._site_engine
        rate_limiter = getattr(engine, "site_limiter", None)
        rate_limiter_engine = rate_limiter.engine if rate_limiter else None
        try:
            html_res = HttpClient(
                config=HttpClientConfig(proxy_url=proxy_url),
                rate_limiter=rate_limiter_engine,
            ).post(url=rss_url, data=data, headers=headers, cookies=site_cookie)
            html_text = html_res.text
        except Exception:
            self.error("生成RSS失败，请检查站点连通性")
            return False, f"[{site}]生成RSS失败，请检查站点连通性"

        if "login.php" in html_text:
            self.error("生成RSS失败，cookie失效")
            return False, f"[{site}]生成RSS失败，cookie失效"

        gen_rss_url = self._parse_rss_link(html_text)
        self.debug(f"生成的rss: {gen_rss_url}")
        if gen_rss_url:
            self._site_repo.update_site_rssurl(site_info.get("id"), gen_rss_url)
            self.info("生成RSS成功")
            return True, f"[{site}]生成RSS成功"
        else:
            self.info("生成RSS失败")
            return True, f"[{site}]生成RSS失败"

    @staticmethod
    def _parse_rss_link(html_text: str) -> str:
        if not html_text:
            return ""

        html = etree.HTML(html_text)
        return next((href for href in cast(list, html.xpath('//a[contains(@href, "linktype=dl")]/@href'))), "")

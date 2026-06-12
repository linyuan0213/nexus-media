from typing import cast

from lxml import etree

from app.plugin_framework.builtin_plugins.autogenrss.backend._autogenrss._base import _ISiteRssGenHandler
from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.utils.config_tools import get_proxies
from app.utils.string_utils import StringUtils


class TTG(_ISiteRssGenHandler):
    """
    TTG
    """

    site_url = "totheglory.im"

    @classmethod
    def match(cls, url):
        return bool(StringUtils.url_equal(url, cls.site_url))

    def gen_rss(self, site_info: dict):
        site = site_info.get("name")
        site_cookie = site_info.get("cookie")
        ua = site_info.get("ua")
        proxy = get_proxies() if site_info.get("proxy") else None

        params = {
            "c47": "47",
            "c28": "28",
            "c45": "45",
            "c49": "49",
            "c5": "5",
            "c105": "105",
            "c26": "26",
            "c104": "104",
            "c29": "29",
            "c46": "46",
            "c107": "107",
            "c110": "110",
            "c44": "44",
            "c106": "106",
            "c27": "27",
            "c43": "43",
            "c48": "48",
            "c33": "33",
            "c30": "30",
            "c31": "31",
            "c51": "51",
            "c52": "52",
            "c53": "53",
            "c54": "54",
            "c108": "108",
            "c109": "109",
            "c62": "62",
            "c63": "63",
            "c67": "67",
            "c69": "69",
            "c70": "70",
            "c73": "73",
            "c76": "76",
            "c75": "75",
            "c74": "74",
            "c87": "87",
            "c88": "88",
            "c99": "99",
            "c90": "90",
            "c77": "77",
            "c32": "32",
            "c56": "56",
            "c82": "82",
            "c83": "83",
            "c59": "59",
            "c57": "57",
            "c58": "58",
            "c103": "103",
            "c101": "101",
            "c60": "60",
            "c91": "91",
            "c84": "84",
            "c92": "92",
            "c93": "93",
            "c94": "94",
            "c95": "95",
            "c111": "111",
        }
        proxy_url = proxy.get("http") if proxy else None
        engine = self._site_engine
        rate_limiter = getattr(engine, "site_limiter", None)
        rate_limiter_engine = rate_limiter.engine if rate_limiter else None
        try:
            html_res = HttpClient(
                config=HttpClientConfig(proxy_url=proxy_url),
                rate_limiter=rate_limiter_engine,
            ).get(
                url="https://totheglory.im/rsstools.php", params=params, headers={"User-Agent": ua}, cookies=site_cookie
            )
            html_text = html_res.text
        except Exception:
            self.error("生成RSS失败，请检查站点连通性")
            return False, f"[{site}]生成RSS失败，请检查站点连通性"

        if "login.php" in html_text:
            self.error("生成RSS失败，cookie失效")
            return False, f"[{site}]生成RSS失败，cookie失效"

        rss_link = self._get_link(html_text)
        self.debug(f"生成的rss: {rss_link}")

        if rss_link:
            self._site_repo.update_site_rssurl(site_info.get("id"), rss_link)
            self.info("生成RSS成功")
            return True, f"[{site}]生成RSS成功"
        else:
            self.info("生成RSS失败")
            return True, f"[{site}]生成RSS失败"

    @staticmethod
    def _get_link(html_text: str) -> str:
        if not html_text:
            return ""

        html = etree.HTML(html_text)
        return next((href for href in cast(list, html.xpath('//textarea[@id="trss"]/text()'))), "")

from typing import cast

from lxml import etree

from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.plugin_framework.builtin_plugins.autogenrss.backend._autogenrss._base import _ISiteRssGenHandler
from app.utils.config_tools import get_proxies
from app.utils.string_utils import StringUtils


class ZhuQue(_ISiteRssGenHandler):
    """
    朱雀
    """

    site_url = "zhuque.in"

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
            ).get(url="https://zhuque.in", headers={"User-Agent": ua}, cookies=site_cookie)
            html_text = html_res.text
        except Exception:
            self.error("生成RSS失败，请检查站点连通性")
            return False, f"[{site}]生成RSS失败，请检查站点连通性"

        if "login.php" in html_text:
            self.error("生成RSS失败，cookie失效")
            return False, f"[{site}]生成RSS失败，cookie失效"

        html = etree.HTML(html_text)

        if not html:
            return False, f"[{site}]生成RSS失败"

        x_csrf_token_list = cast(list, html.xpath("//meta[@name='x-csrf-token']/@content"))
        x_csrf_token = x_csrf_token_list[0] if x_csrf_token_list else None
        if x_csrf_token:
            headers = {
                "x-csrf-token": str(x_csrf_token),
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": ua,
            }
            try:
                security_res = HttpClient(
                    config=HttpClientConfig(proxy_url=proxy_url),
                    rate_limiter=rate_limiter_engine,
                ).get(url="https://zhuque.in/api/user/getSecurityInfo", headers=headers, cookies=site_cookie)
                json_data = security_res.json()
            except Exception:
                self.error("生成RSS失败")
                return False, f"[{site}]生成RSS失败"
        else:
            return False, f"[{site}]生成RSS失败"

        rss_link = ""
        if json_data.get("status") == 200:
            rss_key = json_data.get("data").get("rssKey")
            torrent_key = json_data.get("data").get("torrentKey")
            rss_link = f"https://zhuque.in/api/torrent/rss/{rss_key}/{torrent_key}"
            self.debug(f"生成的rss: {rss_link}")

            self._site_repo.update_site_rssurl(site_info.get("id"), rss_link)
            self.info("生成RSS成功")
            return True, f"[{site}]生成RSS成功"
        else:
            self.info("生成RSS失败")
            return True, f"[{site}]生成RSS失败"

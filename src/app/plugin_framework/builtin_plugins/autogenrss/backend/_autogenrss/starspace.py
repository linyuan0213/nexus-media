from typing import cast

from lxml import etree

from app.plugin_framework.builtin_plugins.autogenrss.backend._autogenrss._base import _ISiteRssGenHandler
from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.sites.engine import SiteEngine
from app.utils.config_tools import get_proxies
from app.utils.string_utils import StringUtils
from app.di import container


class Ourbits(_ISiteRssGenHandler):
    """
    star-space
    """

    site_url = "star-space.net"

    @classmethod
    def match(cls, url):
        return bool(StringUtils.url_equal(url, cls.site_url))

    def gen_rss(self, site_info: dict):
        site = site_info.get("name")
        site_cookie = site_info.get("cookie")
        ua = site_info.get("ua")
        proxy = get_proxies() if site_info.get("proxy") else None
        proxy_url = proxy.get("http") if proxy else None
        engine = SiteEngine.get_instance()
        rate_limiter = getattr(engine, "site_limiter", None)
        rate_limiter_engine = rate_limiter.engine if rate_limiter else None

        try:
            html_res = HttpClient(
                config=HttpClientConfig(proxy_url=proxy_url),
                rate_limiter=rate_limiter_engine,
            ).get(url="https://star-space.net/p_rss/rss_create.php", headers={"User-Agent": ua}, cookies=site_cookie)
            html_text = html_res.text
        except Exception:
            self.error("生成RSS失败，请检查站点连通性")
            return False, f"[{site}]生成RSS失败，请检查站点连通性"

        if "login_act.php" in html_text:
            self.error("生成RSS失败，cookie失效")
            return False, f"[{site}]生成RSS失败，cookie失效"
        rss_link = self._get_rss_link(html_text)

        if not rss_link:
            data = {"cat": "", "media": "", "btn_add": "创建RSS"}
            headers = {
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,ja;q=0.7",
                "content-type": "application/x-www-form-urlencoded",
                "origin": "https://star-space.net",
                "referer": "https://star-space.net/p_rss/rss_create.php",
                "user-agent": ua,
            }
            try:
                post_res = HttpClient(
                    config=HttpClientConfig(proxy_url=proxy_url),
                    rate_limiter=rate_limiter_engine,
                ).post(url="https://star-space.net/p_rss/rss_act.php", data=data, headers=headers, cookies=site_cookie)
            except Exception:
                self.error("生成RSS失败，请检查站点连通性")
                return False, f"[{site}]生成RSS失败，请检查站点连通性"

            if "操作成功" in post_res.text:
                try:
                    html_res = HttpClient(
                        config=HttpClientConfig(proxy_url=proxy_url),
                        rate_limiter=rate_limiter_engine,
                    ).get(
                        url="https://star-space.net/p_rss/rss_create.php",
                        headers={"User-Agent": ua},
                        cookies=site_cookie,
                    )
                    html_text = html_res.text
                except Exception:
                    self.error("生成RSS失败，请检查站点连通性")
                    return False, f"[{site}]生成RSS失败，请检查站点连通性"
                rss_link = self._get_rss_link(html_text)
        self.debug(f"生成的rss: {rss_link}")

        if rss_link:
            container.site_repository().update_site_rssurl(site_info.get("id"), rss_link)
            self.info("生成RSS成功")
            return True, f"[{site}]生成RSS成功"
        else:
            self.info("生成RSS失败")
            return True, f"[{site}]生成RSS失败"

    @staticmethod
    def _get_rss_link(html_text: str) -> str:
        if not html_text:
            return ""
        html = etree.HTML(html_text)
        return next((href for href in cast(list, html.xpath('//a[contains(@href, "rss.php?key=")]/@href'))), "")

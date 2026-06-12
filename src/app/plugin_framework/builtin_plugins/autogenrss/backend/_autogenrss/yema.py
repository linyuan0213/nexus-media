import json

from app.plugin_framework.builtin_plugins.autogenrss.backend._autogenrss._base import _ISiteRssGenHandler
from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.utils.config_tools import get_proxies
from app.utils.string_utils import StringUtils


class YemaPT(_ISiteRssGenHandler):
    """
    YemaPT
    """

    site_url = "yemapt.org"

    @classmethod
    def match(cls, url):
        return bool(StringUtils.url_equal(url, cls.site_url))

    def gen_rss(self, site_info: dict):
        site = site_info.get("name")
        site_cookie = site_info.get("cookie")
        ua = site_info.get("ua")
        proxy = get_proxies() if site_info.get("proxy") else None
        headers = {"accept": "application/json, text/plain, */*", "content-type": "application/json", "user-agent": ua}

        rss_url = "https://www.yemapt.org/api/rss/generateRssUrl"
        data = {"categoryIdList": [], "withShortDesc": True, "withSize": True, "showPromotion": False, "pageSize": 50}
        data = json.dumps(data, separators=(",", ":"))

        proxy_url = proxy.get("http") if proxy else None
        engine = self._site_engine
        rate_limiter = getattr(engine, "site_limiter", None)
        rate_limiter_engine = rate_limiter.engine if rate_limiter else None
        try:
            res = HttpClient(
                config=HttpClientConfig(proxy_url=proxy_url),
                rate_limiter=rate_limiter_engine,
            ).post(url=rss_url, data=data, headers=headers, cookies=site_cookie)
            json_data = res.json()
        except Exception:
            self.error("生成RSS失败，请检查站点连通性")
            return False, f"[{site}]生成RSS失败"

        rss_link = ""
        if json_data.get("success"):
            rss_link = json_data.get("data")
            self.debug(f"生成的rss: {rss_link}")

        if rss_link:
            self._site_repo.update_site_rssurl(site_info.get("id"), rss_link)
            self.info("生成RSS成功")
            return True, f"[{site}]生成RSS成功"
        else:
            self.info("生成RSS失败")
            return True, f"[{site}生成RSS失败"

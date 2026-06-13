from app.core.constants import MT_URL
from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.plugin_framework.builtin_plugins.autogenrss.backend._autogenrss._base import _ISiteRssGenHandler
from app.utils.config_tools import get_proxies
from app.utils.json_utils import JsonUtils


class Mteam(_ISiteRssGenHandler):
    """
    m-team
    """

    site_url = "m-team"

    @classmethod
    def match(cls, url):
        return cls.site_url in url

    def gen_rss(self, site_info: dict):
        site = site_info.get("name")
        ua = site_info.get("ua")
        headers = JsonUtils.loads(site_info.get("headers") or "{}")
        headers.update({"contentType": "application/json;charset=UTF-8", "User-Agent": ua})

        proxy = get_proxies() if site_info.get("proxy") else None

        rss_url = f"{MT_URL}/api/rss/genlink"
        data = {"labels": 0, "tkeys": ["ttitle", "tcat", "tsmalldescr", "tsize"], "pageSize": 50}
        data = JsonUtils.dumps(data, separators=(",", ":"))

        proxy_url = proxy.get("http") if proxy else None
        engine = self._site_engine
        rate_limiter = getattr(engine, "site_limiter", None)
        rate_limiter_engine = rate_limiter.engine if rate_limiter else None
        try:
            res = HttpClient(
                config=HttpClientConfig(proxy_url=proxy_url),
                rate_limiter=rate_limiter_engine,
            ).post(url=rss_url, data=data, headers=headers)
            json_data = res.json()
        except Exception:
            self.error("生成RSS失败，请检查站点连通性")
            return False, f"[{site}]生成RSS失败"

        rss_link = ""
        if json_data.get("message") == "SUCCESS":
            rss_link = json_data.get("data").get("dlUrl")
            self.debug(f"生成的rss: {rss_link}")

        if rss_link:
            self._site_repo.update_site_rssurl(site_info.get("id"), rss_link)
            self.info("生成RSS成功")
            return True, f"[{site}]生成RSS成功"
        else:
            self.info("生成RSS失败")
            return True, f"[{site}生成RSS失败"

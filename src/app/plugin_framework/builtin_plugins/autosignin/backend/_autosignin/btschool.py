from app.plugin_framework.builtin_plugins.autosignin.backend._autosignin._base import _ISiteSigninHandler
from app.infrastructure.http.auth import CookieAuth
from app.infrastructure.http.client import HttpClient, HttpClientError
from app.infrastructure.http.config import HttpClientConfig
from app.utils import StringUtils
from app.utils.config_tools import get_proxies
from app.di import container


class BTSchool(_ISiteSigninHandler):
    site_url = "pt.btschool.club"
    _sign_text = "每日签到"

    @classmethod
    def match(cls, url):
        return bool(StringUtils.url_equal(url, cls.site_url))

    def signin(self, site_info: dict):
        site = site_info.get("name")
        site_cookie = site_info.get("cookie")
        ua = site_info.get("ua")
        proxy = get_proxies() if site_info.get("proxy") else None

        chrome = container.drissionpage_helper()
        if site_info.get("chrome") and chrome.get_status():
            self.info(f"{site} 开始仿真签到")
            msg, html_text = self.__chrome_visit(
                chrome=chrome,
                url="https://pt.btschool.club/index.php",
                ua=ua,
                site_cookie=site_cookie,
                proxy=proxy,
                site=site,
            )
            if msg or not html_text:
                return False, msg
            if self._sign_text not in html_text:
                self.info("今日已签到")
                return True, f"[{site}]今日已签到"
            msg, html_text = self.__chrome_visit(
                chrome=chrome,
                url="https://pt.btschool.club/index.php?action=addbonus",
                ua=ua,
                site_cookie=site_cookie,
                proxy=proxy,
                site=site,
            )
            if msg or not html_text:
                return False, msg
            if self._sign_text not in html_text:
                self.info("签到成功")
                return True, f"[{site}]签到成功"
        else:
            self.info(f"{site} 开始签到")
            try:
                html_res = HttpClient(
                    config=HttpClientConfig(proxy_url=proxy.get("http") if proxy else None),
                ).get(
                    url="https://pt.btschool.club",
                    headers={"User-Agent": ua} if ua else None,
                    auth=CookieAuth(site_cookie) if site_cookie else None,
                )
            except HttpClientError:
                self.error("签到失败，请检查站点连通性")
                return False, f"[{site}]签到失败，请检查站点连通性"

            if html_res.status_code != 200:
                self.error("签到失败，请检查站点连通性")
                return False, f"[{site}]签到失败，请检查站点连通性"
            if "login.php" in html_res.text:
                self.error("签到失败，cookie失效")
                return False, f"[{site}]签到失败，cookie失效"
            if self._sign_text not in html_res.text:
                self.info("今日已签到")
                return True, f"[{site}]今日已签到"

            try:
                sign_res = HttpClient(
                    config=HttpClientConfig(proxy_url=proxy.get("http") if proxy else None),
                ).get(
                    url="https://pt.btschool.club/index.php?action=addbonus",
                    headers={"User-Agent": ua} if ua else None,
                    auth=CookieAuth(site_cookie) if site_cookie else None,
                )
            except HttpClientError:
                self.error("签到失败，签到接口请求失败")
                return False, f"[{site}]签到失败，签到接口请求失败"

            if sign_res.status_code != 200:
                self.error("签到失败，签到接口请求失败")
                return False, f"[{site}]签到失败，签到接口请求失败"
            if self._sign_text not in sign_res.text:
                self.info("签到成功")
                return True, f"[{site}]签到成功"

    def __chrome_visit(self, chrome, url, ua, site_cookie, proxy, site):
        html_text = chrome.get_page_html(url=url, cookies=site_cookie)
        if not html_text:
            self.warn(f"{site} 获取站点源码失败")
            return f"[{site}]仿真签到失败，获取站点源码失败！", None
        if "魔力值" not in html_text:
            self.error("签到失败，站点无法访问")
            return f"[{site}]仿真签到失败，站点无法访问", None
        return None, html_text

import json
from typing import cast

from lxml import etree

from app.infrastructure.http.client import HttpClient, HttpClientError
from app.infrastructure.http.config import HttpClientConfig
from app.infrastructure.http.auth import CookieAuth
from app.plugin_framework.builtin_plugins.autosignin.backend._autosignin._base import _ISiteSigninHandler
from app.utils import StringUtils
from app.utils.config_tools import get_proxies


class ZhuQue(_ISiteSigninHandler):
    """
    ZHUQUE签到
    """

    # 匹配的站点Url，每一个实现类都需要设置为自己的站点Url
    site_url = "zhuque.in"

    @classmethod
    def match(cls, url):
        """
        根据站点Url判断是否匹配当前站点签到类，大部分情况使用默认实现即可
        :param url: 站点Url
        :return: 是否匹配，如匹配则会调用该类的signin方法
        """
        return bool(StringUtils.url_equal(url, cls.site_url))

    def signin(self, site_info: dict):
        """
        执行签到操作
        :param site_info: 站点信息，含有站点Url、站点Cookie、UA等信息
        :return: 签到结果信息
        """
        site = site_info.get("name")
        site_cookie = site_info.get("cookie")
        ua = site_info.get("ua")
        proxy = get_proxies() if site_info.get("proxy") else None

        # 获取页面html
        try:
            html_res = HttpClient(config=HttpClientConfig(proxy_url=proxy.get("http") if proxy else None)).get(
                url="https://zhuque.in",
                headers={"User-Agent": ua} if ua else None,
                auth=CookieAuth(site_cookie) if site_cookie else None,
                raise_for_status=False,
            )
        except HttpClientError:
            self.error("模拟登录失败，请检查站点连通性")
            return False, f"[{site}]模拟登录失败，请检查站点连通性"

        if not html_res or html_res.status_code != 200:
            self.error("模拟登录失败，请检查站点连通性")
            return False, f"[{site}]模拟登录失败，请检查站点连通性"

        if "login.php" in html_res.text:
            self.error("模拟登录失败，cookie失效")
            return False, f"[{site}]模拟登录失败，cookie失效"

        html = etree.HTML(html_res.text)

        if not html:
            return False, f"[{site}]模拟登录失败"

        # 释放技能
        msg = "失败"
        x_csrf_token = cast(list, html.xpath("//meta[@name='x-csrf-token']/@content"))[0]
        if x_csrf_token:
            data = {"all": 1, "resetModal": "true"}
            headers = {
                "x-csrf-token": str(x_csrf_token),
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": ua,
            }
            try:
                skill_res = HttpClient(config=HttpClientConfig(proxy_url=proxy.get("http") if proxy else None)).post(
                    url="https://zhuque.in/api/gaming/fireGenshinCharacterMagic",
                    json=data,
                    headers=headers,
                    auth=CookieAuth(site_cookie) if site_cookie else None,
                    raise_for_status=False,
                )
            except HttpClientError:
                self.error("模拟登录失败，释放技能失败")
                return False, f"[{site}]模拟登录失败，释放技能失败"

            if not skill_res or skill_res.status_code != 200:
                self.error("模拟登录失败，释放技能失败")
                return False, f"[{site}]模拟登录失败，释放技能失败"

            # '{"status":200,"data":{"code":"FIRE_GENSHIN_CHARACTER_MAGIC_SUCCESS","bonus":0}}'
            skill_dict = json.loads(skill_res.text)
            if skill_dict["status"] == 200:
                bonus = int(skill_dict["data"]["bonus"])
                msg = f"成功，获得{bonus}魔力"

        self.info(f"[{site}]模拟登录成功，技能释放{msg}")
        return True, f"[{site}]模拟登录成功，技能释放{msg}"

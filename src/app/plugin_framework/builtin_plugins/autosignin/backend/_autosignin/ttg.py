import re

from app.infrastructure.http.auth import CookieAuth
from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.plugin_framework.builtin_plugins.autosignin.backend._autosignin._base import _ISiteSigninHandler
from app.sites.engine import SiteEngine
from app.utils import StringUtils
from app.utils.config_tools import get_proxies


class TTG(_ISiteSigninHandler):
    """
    TTG签到
    """

    # 匹配的站点Url，每一个实现类都需要设置为自己的站点Url
    site_url = "totheglory.im"

    # 已签到
    _sign_regex = ['<b style="color:green;">已签到</b>']
    _sign_text = "亲，您今天已签到过，不要太贪哦"

    # 签到成功
    _success_text = "您已连续签到"

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
        engine = SiteEngine.get_instance()
        rate_limiter = getattr(engine, "site_limiter", None)
        rate_limiter_engine = rate_limiter.engine if rate_limiter else None
        site_id = site_info.get("id")
        rl_kwargs = {}
        if site_id and rate_limiter:
            rate_config = rate_limiter.get_rate(str(site_id))
            if rate_config:
                rl_kwargs = {"rate_limit_key": f"site:{site_id}", "rate_limit_rate": rate_config[0]}

        # 获取页面html
        proxy_url = proxy.get("http") if isinstance(proxy, dict) else proxy
        try:
            html_res = HttpClient(config=HttpClientConfig(proxy_url=proxy_url), rate_limiter=rate_limiter_engine).get(
                url="https://totheglory.im",
                headers={"User-Agent": ua} if ua else None,
                cookies=CookieAuth._parse_cookies(site_cookie),
                **rl_kwargs,
            )
        except Exception:
            self.error("签到失败，请检查站点连通性")
            return False, f"[{site}]签到失败，请检查站点连通性"

        if "login.php" in html_res.text:
            self.error("签到失败，cookie失效")
            return False, f"[{site}]签到失败，cookie失效"

        # 判断是否已签到
        html_res.encoding = "utf-8"
        sign_status = self.sign_in_result(html_res=html_res.text, regexs=self._sign_regex)
        if sign_status:
            self.info("今日已签到")
            return True, f"[{site}]今日已签到"

        # 获取签到参数
        signed_timestamp_match = re.search('(?<=signed_timestamp: ")\\d{10}', html_res.text)
        signed_token_match = re.search('(?<=signed_token: ").*(?=")', html_res.text)
        if not signed_timestamp_match or not signed_token_match:
            self.error("签到失败，无法获取签到参数")
            return False, f"[{site}]签到失败，无法获取签到参数"
        signed_timestamp = signed_timestamp_match.group()
        signed_token = signed_token_match.group()
        self.debug(f"signed_timestamp={signed_timestamp} signed_token={signed_token}")

        data = {"signed_timestamp": signed_timestamp, "signed_token": signed_token}
        # 签到
        try:
            sign_res = HttpClient(config=HttpClientConfig(proxy_url=proxy_url), rate_limiter=rate_limiter_engine).post(
                url="https://totheglory.im/signed.php",
                data=data,
                headers={"User-Agent": ua} if ua else None,
                cookies=CookieAuth._parse_cookies(site_cookie),
                **rl_kwargs,
            )
        except Exception:
            self.error("签到失败，签到接口请求失败")
            return False, f"[{site}]签到失败，签到接口请求失败"

        sign_res.encoding = "utf-8"
        if self._success_text in sign_res.text:
            self.info("签到成功")
            return True, f"[{site}]签到成功"
        if self._sign_text in sign_res.text:
            self.info("今日已签到")
            return True, f"[{site}]今日已签到"

        self.error("签到失败，未知原因")
        return False, f"[{site}]签到失败，未知原因"

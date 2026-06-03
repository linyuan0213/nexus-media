import json
import time

from app.infrastructure.ocr import OcrRecognizer
from app.infrastructure.http.auth import CookieAuth
from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.plugin_framework.builtin_plugins.autosignin.backend._autosignin._base import _ISiteSigninHandler
from app.sites.engine import SiteEngine
from app.utils import StringUtils
from app.utils.config_tools import get_proxies


class HDSky(_ISiteSigninHandler):
    """
    天空ocr签到
    """

    # 匹配的站点Url，每一个实现类都需要设置为自己的站点Url
    site_url = "hdsky.me"

    # 已签到
    _sign_regex = ["已签到"]

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

        # 判断今日是否已签到
        proxy_url = proxy.get("http") if isinstance(proxy, dict) else proxy
        engine = SiteEngine.get_instance()
        rate_limiter = getattr(engine, "site_limiter", None)
        rate_limiter_engine = rate_limiter.engine if rate_limiter else None
        try:
            index_res = HttpClient(config=HttpClientConfig(proxy_url=proxy_url), rate_limiter=rate_limiter_engine).get(
                url="https://hdsky.me",
                headers={"User-Agent": ua} if ua else None,
                cookies=CookieAuth._parse_cookies(site_cookie),
            )
        except Exception:
            self.error("签到失败，请检查站点连通性")
            return False, f"[{site}]签到失败，请检查站点连通性"

        if "login.php" in index_res.text:
            self.error("签到失败，cookie失效")
            return False, f"[{site}]签到失败，cookie失效"

        sign_status = self.sign_in_result(html_res=index_res.text, regexs=self._sign_regex)
        if sign_status:
            self.info("今日已签到")
            return True, f"[{site}]今日已签到"

        # 获取验证码请求，考虑到网络问题获取失败，多获取几次试试
        res_times = 0
        img_hash = None
        image_headers = (
            {"User-Agent": ua, "Referer": "https://hdsky.me/index.php"}
            if ua
            else {"Referer": "https://hdsky.me/index.php"}
        )
        while not img_hash and res_times <= 3:
            try:
                _client = HttpClient(
                    config=HttpClientConfig(proxy_url=proxy_url),
                    rate_limiter=rate_limiter_engine,
                )
                image_res = _client.post(
                    url="https://hdsky.me/image_code_ajax.php",
                    data={"action": "new"},
                    headers=image_headers,
                    cookies=CookieAuth._parse_cookies(site_cookie),
                )
                image_json = json.loads(image_res.text)
                if image_json["success"]:
                    img_hash = image_json["code"]
                    break
                res_times += 1
                self.debug(f"获取{site}验证码失败，正在进行重试，目前重试次数 {res_times}")
                time.sleep(1)
            except Exception:
                pass

        # 获取到二维码hash
        if img_hash:
            # 完整验证码url
            img_get_url = f"https://hdsky.me/image.php?action=regimage&imagehash={img_hash}"
            self.debug(f"获取到{site}验证码链接 {img_get_url}")
            # ocr识别多次，获取6位验证码
            times = 0
            ocr_result = None
            # 识别几次
            while times <= 3:
                # ocr二维码识别
                ocr_result = OcrRecognizer().get_captcha_text(image_url=img_get_url, cookie=site_cookie, ua=ua)
                self.debug(f"ocr识别{site}验证码 {ocr_result}")
                if ocr_result:
                    if len(ocr_result) == 6:
                        self.info(f"ocr识别{site}验证码成功 {ocr_result}")
                        break
                times += 1
                self.debug(f"ocr识别{site}验证码失败，正在进行重试，目前重试次数 {times}")
                time.sleep(1)

            if ocr_result:
                # 组装请求参数
                data = {"action": "showup", "imagehash": img_hash, "imagestring": ocr_result}
                # 访问签到链接
                try:
                    _client = HttpClient(
                        config=HttpClientConfig(proxy_url=proxy_url),
                        rate_limiter=rate_limiter_engine,
                    )
                    res = _client.post(
                        url="https://hdsky.me/showup.php",
                        data=data,
                        headers=image_headers,
                        cookies=CookieAuth._parse_cookies(site_cookie),
                    )
                    if json.loads(res.text)["success"]:
                        self.info("签到成功")
                        return True, f"[{site}]签到成功"
                    elif str(json.loads(res.text)["message"]) == "date_unmatch":
                        # 重复签到
                        self.warn("重复成功")
                        return True, f"[{site}]今日已签到"
                    elif str(json.loads(res.text)["message"]) == "invalid_imagehash":
                        # 验证码错误
                        self.warn("签到失败：验证码错误")
                        return False, f"[{site}]签到失败：验证码错误"
                except Exception:
                    pass

        self.error("签到失败：未获取到验证码")
        return False, f"[{site}]签到失败：未获取到验证码"

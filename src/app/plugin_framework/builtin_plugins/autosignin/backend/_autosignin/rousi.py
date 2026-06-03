import json
import time

from app.infrastructure.cache_system.cookiecloud_adapter import CookiecloudAdapter
from app.infrastructure.http.auth import BearerAuth
from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.infrastructure.http.exceptions import HttpClientError
from app.plugin_framework.builtin_plugins.autosignin.backend._autosignin._base import _ISiteSigninHandler
from app.plugin_framework.hook_system import HookSystem
from app.sites.engine import SiteEngine
from app.utils import StringUtils
from app.utils.config_tools import get_proxies


class Rousi(_ISiteSigninHandler):
    """
    馒头登录
    """

    # 匹配的站点Url，每一个实现类都需要设置为自己的站点Url
    site_url = "rousi.pro"

    # 已签到
    _sign_text = "已签到"

    @classmethod
    def match(cls, url):
        """
        根据站点Url判断是否匹配当前站点签到类，大部分情况使用默认实现即可
        :param url: 站点Url
        :return: 是否匹配，如匹配则会调用该类的signin方法
        """
        return bool(StringUtils.url_equal(url, cls.site_url))

    def _get_sign_token(self, site_info: dict):
        """
        获取用于签到的token
        优先级：
        1. 从local_storage获取
        2. 从site_info的headers中获取x-sign-token或sign-authorization字段
        3. 从site_info的headers中获取authorization字段（如果允许复用）
        """
        # 首先尝试从local_storage获取
        local_storage = CookiecloudAdapter().get_local_storage("rousi.pro")
        if local_storage:
            token = local_storage.get("token")
            if token:
                return token

        # 从site_info的headers中获取
        headers = site_info.get("headers")
        if headers:
            if isinstance(headers, str):
                try:
                    headers = json.loads(headers)
                except Exception:
                    headers = None

            if isinstance(headers, dict):
                # 优先查找专门用于签到的token字段（不区分大小写）
                for key in headers:
                    if key.lower() in ["x-sign-token", "sign-authorization", "x-sign-authorization"]:
                        token = headers[key]
                        # 如果token已经是Bearer格式，提取实际token值
                        if token and token.startswith("Bearer "):
                            token = token[7:]
                        return token

                # 如果没有专门的签到token字段，尝试从authorization提取
                # 注意：这里的authorization可能不适用于签到，仅作为备用
                for key in headers:
                    if key.lower() == "authorization":
                        auth = headers[key]
                        if auth and auth.startswith("Bearer "):
                            # 返回完整的Bearer token格式
                            return auth[7:]
                        elif auth:
                            return auth

        return None

    def signin(self, site_info: dict):
        """
        执行签到操作
        :param site_info: 站点信息，含有站点Url、站点Cookie、UA等信息
        :return: 签到结果信息
        """
        site = site_info.get("name")
        ua = site_info.get("ua")
        proxy = get_proxies() if site_info.get("proxy") else None

        HookSystem().emit("site.local_storage_sync", {})
        time.sleep(10)

        # 获取签到token
        token = self._get_sign_token(site_info)

        if not token:
            self.error(
                "签到失败，无法获取签到token，请检查LocalStorage或站点Headers中的x-sign-token/sign-authorization配置"
            )
            return False, f"[{site}]签到失败，无法获取签到token"
        self.info(f"{site} 开始签到")

        proxy_url = proxy.get("http") if isinstance(proxy, dict) else proxy
        engine = SiteEngine.get_instance()
        rate_limiter = getattr(engine, "site_limiter", None)
        rate_limiter_engine = rate_limiter.engine if rate_limiter else None
        res_text = None
        try:
            res = HttpClient(
                config=HttpClientConfig(proxy_url=proxy_url, timeout=30.0, auth=BearerAuth(token)),
                rate_limiter=rate_limiter_engine,
            ).post(
                url="https://rousi.pro/api/points/attendance",
                data='{"mode":"fixed"}',
                headers={
                    "accept": "application/json, text/plain, */*",
                    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,ja;q=0.7",
                    "content-type": "application/json",
                    "origin": "https://rousi.pro",
                    "referer": "https://rousi.pro/",
                    "User-Agent": ua,
                },
            )
            res_text = res.text
        except HttpClientError as e:
            if e.status_code is not None and e.response_text:
                res_text = e.response_text

        if res_text is None:
            self.warn(f"{site} 获取签到接口响应失败")
            return False, f"[{site}]签到失败，获取签到接口响应失败！"

        try:
            res_json = json.loads(res_text)
        except Exception as e:
            self.warn(f"{site} 解析响应JSON失败: {str(e)}")
            return False, f"[{site}]签到失败，解析响应失败！"

        # code 0 表示首次签到成功
        if res_json.get("code") == 0:
            self.info("签到成功")
            return True, f"[{site}]签到成功"

        # code 1 表示已经签到过了（可能是400状态码返回的）
        if res_json.get("code") == 1:
            message = res_json.get("message", "")
            if "已签到" in message or "签到" in message:
                self.info("已签到")
                return True, f"[{site}]已签到"

        # 其他情况视为失败
        self.warn("{} 签到接口返回错误，code: {}, 信息：{}".format(site, res_json.get("code"), res_json.get("message")))
        return False, f"[{site}]签到失败，信息：{res_json.get('message')}"

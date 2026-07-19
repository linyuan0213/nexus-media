import hashlib
import logging
import time

from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.utils.json_utils import JsonUtils

_logger = logging.getLogger(__name__)


class IyuuHelper:
    _version = "2.0.0"
    _api_base = "https://2025.iyuu.cn%s"
    _rate_limit_key = "plugin:iyuuautoseed:iyuu_api"
    _default_rate_limit = "1/30s"

    def __init__(self, token, site_engine=None, rate_limit: str = ""):
        self._token = token
        self._sites = {}
        self._site_engine = site_engine
        self._rate_limit = (rate_limit or self._default_rate_limit).strip()

    def __request_iyuu(self, url, method="get", params=None, json_body=False):
        """
        向IYUUApi发送请求
        """
        headers = {"token": self._token, "Accept": "application/json"}
        rate_limiter = getattr(self._site_engine, "site_limiter", None)
        rate_limiter_engine = rate_limiter.engine if rate_limiter else None
        # 主动阻塞限流：等待直到获取令牌
        if rate_limiter_engine and self._rate_limit:
            rate_limiter_engine.acquire(
                key=self._rate_limit_key,
                rate=self._rate_limit,
                timeout=120.0,
            )
        # 开始请求
        try:
            if method == "get":
                res = HttpClient(
                    config=HttpClientConfig(default_headers=headers),
                ).get(f"{url}", params=params)
            else:
                if json_body:
                    res = HttpClient(
                        config=HttpClientConfig(default_headers=headers),
                    ).post(f"{url}", json=params)
                else:
                    res = HttpClient(
                        config=HttpClientConfig(default_headers=headers),
                    ).post(f"{url}", data=params)
            result = res.json()
            if result.get("code") == 0:
                return result.get("data"), ""
            else:
                return None, f"请求IYUU失败，状态码：{result.get('code')}，返回信息：{result.get('msg')}"
        except Exception as exc:
            return None, f"请求IYUU失败：{exc}"

    def get_torrent_url(self, sid):
        """返回站点 (base_url, download_page, is_https)，is_https: 0=仅http，其他=https"""
        if not sid:
            return None, None, None
        if not self._sites:
            self._sites = self.__get_sites()
        site = self._sites.get(sid)
        if not site:
            return None, None, None
        return site.get("base_url"), site.get("download_page"), site.get("is_https")

    def __get_sites(self):
        """
        返回支持辅种的全部站点
        :return: 站点列表、错误信息
        {
            "ret": 200,
            "data": {
                "sites": [
                    {
                        "id": 1,
                        "site": "keepfrds",
                        "nickname": "朋友",
                        "base_url": "pt.keepfrds.com",
                        "download_page": "download.php?id={}&passkey={passkey}",
                        "reseed_check": "passkey",
                        "is_https": 2
                    },
                ]
            }
        }
        """
        result, msg = self.__request_iyuu(url=self._api_base % "/reseed/sites/index")
        if result:
            ret_sites = {}
            sites = result.get("sites") or []
            for site in sites:
                ret_sites[site.get("id")] = site
            return ret_sites
        else:
            _logger.error(msg)
            return {}

    def get_seed_info(self, info_hashs: list):
        """
        返回info_hash对应的站点id、种子id
        {
            "code": 0,
            "data": {
                "7866fdafbcc5ad504c7750f2d4626dc03954c50a": {
                    "torrent": [
                        {
                            "sid": 32,
                            "torrent_id": 19537,
                            "info_hash": "93665ee3f41f1845c6628b105b2d236cc08b9826"
                        },
                        {
                            "sid": 14,
                            "torrent_id": 413945,
                            "info_hash": "9e2e41fba99d135db84585419703906ec710e241"
                        }
                    ]
                }
            },
            "msg": "ok"
        }
        """
        sites = self.__get_sites()
        site_ids = list(sites.keys())
        if not site_ids:
            return None, "无法获取 IYUU 站点列表（可能被限流），请稍后重试"
        result, msg = self.__request_iyuu(
            url=self._api_base % "/reseed/sites/reportExisting",
            method="post",
            params={"sid_list": site_ids},
            json_body=True,
        )
        if not result:
            return result, msg
        sid_sha1 = result.get("sid_sha1")

        info_hashs.sort()
        json_data = JsonUtils.dumps(info_hashs, separators=(",", ":"), ensure_ascii=False)
        sha1 = self.get_sha1(json_data)
        result, msg = self.__request_iyuu(
            url=self._api_base % "/reseed/index/index",
            method="post",
            params={
                "timestamp": int(time.time()),
                "hash": json_data,
                "sid_sha1": sid_sha1,
                "sha1": sha1,
                "version": "8.2.0",
            },
        )
        return result, msg

    @staticmethod
    def get_sha1(json_str) -> str:
        return hashlib.sha1(json_str.encode("utf-8"), usedforsecurity=False).hexdigest()

    def get_auth_sites(self):
        """
        返回支持鉴权的站点列表及错误信息
        ([{"id": 2, "site": "pthome", "nickname": "铂金家"}], "")
        """
        result, msg = self.__request_iyuu(url=self._api_base % "/reseed/sites/recommend")
        if msg:
            _logger.error(msg)
            return [], msg
        return (result or {}).get("list") or [], ""

    def bind_site(self, site, passkey, uid):
        """
        绑定站点
        :param site: 站点名称
        :param passkey: passkey
        :param uid: 用户id
        :return: 状态码、错误信息
        """
        sites, msg = self.get_auth_sites()
        if msg:
            return None, msg
        sid = ""
        for site_info in sites:
            if site_info.get("site") == site:
                sid = site_info.get("id")
                break
        if not sid:
            return None, "获取站点id失败"
        result, msg = self.__request_iyuu(
            url=self._api_base % "/reseed/users/bind",
            method="post",
            params={"token": self._token, "site": site, "passkey": self.get_sha1(passkey), "id": uid, "sid": sid},
        )
        return result, msg

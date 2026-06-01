import json
import logging
import os
import time
from functools import lru_cache

import requests
import requests.exceptions

from app.utils.tmdb_rate_limiter import get_rate_limiter, get_retry_handler

from .as_obj import AsObj
from .exceptions import TMDbError

logger = logging.getLogger(__name__)


class TMDb:
    TMDB_API_KEY = "TMDB_API_KEY"
    TMDB_LANGUAGE = "TMDB_LANGUAGE"
    TMDB_WAIT_ON_RATE_LIMIT = "TMDB_WAIT_ON_RATE_LIMIT"
    TMDB_DEBUG_ENABLED = "TMDB_DEBUG_ENABLED"
    TMDB_CACHE_ENABLED = "TMDB_CACHE_ENABLED"
    TMDB_PROXIES = "TMDB_PROXIES"
    TMDB_DOMAIN = "TMDB_DOMAIN"
    REQUEST_CACHE_MAXSIZE = 512

    def __init__(self, obj_cached=True, session=None):
        self._session = requests.Session() if session is None else session
        self._remaining = 40
        self._reset = None
        self.obj_cached = obj_cached
        if os.environ.get(self.TMDB_LANGUAGE) is None:
            os.environ[self.TMDB_LANGUAGE] = "zh"
        if not os.environ.get(self.TMDB_DOMAIN):
            os.environ[self.TMDB_DOMAIN] = "https://api.themoviedb.org/3"

    @property
    def page(self):
        return os.environ["PAGE"]

    @property
    def total_results(self):
        return os.environ["TOTAL_RESULTS"]

    @property
    def total_pages(self):
        return os.environ["TOTAL_PAGES"]

    @property
    def api_key(self):
        return os.environ.get(self.TMDB_API_KEY)

    @property
    def domain(self):
        return os.environ.get(self.TMDB_DOMAIN)

    @domain.setter
    def domain(self, domain):
        os.environ[self.TMDB_DOMAIN] = str(domain or "")

    @property
    def proxies(self):
        return os.environ.get(self.TMDB_PROXIES)

    @proxies.setter
    def proxies(self, proxies):
        if proxies:
            proxies_strs = []
            for key, value in proxies.items():
                if not value:
                    continue
                proxies_strs.append(f"'{key}': '{value}'")
            if proxies_strs:
                os.environ[self.TMDB_PROXIES] = "{{{}}}".format(",".join(proxies_strs))
            else:
                os.environ[self.TMDB_PROXIES] = "None"

    @api_key.setter
    def api_key(self, api_key):
        os.environ[self.TMDB_API_KEY] = str(api_key)

    @property
    def language(self):
        return os.environ.get(self.TMDB_LANGUAGE)

    @language.setter
    def language(self, language):
        os.environ[self.TMDB_LANGUAGE] = language

    @property
    def wait_on_rate_limit(self):
        return os.environ.get(self.TMDB_WAIT_ON_RATE_LIMIT) != "False"

    @wait_on_rate_limit.setter
    def wait_on_rate_limit(self, wait_on_rate_limit):
        os.environ[self.TMDB_WAIT_ON_RATE_LIMIT] = str(wait_on_rate_limit)

    @property
    def debug(self):
        return os.environ.get(self.TMDB_DEBUG_ENABLED) == "True"

    @debug.setter
    def debug(self, debug):
        os.environ[self.TMDB_DEBUG_ENABLED] = str(debug)

    @property
    def cache(self):
        return os.environ.get(self.TMDB_CACHE_ENABLED) != "False"

    @cache.setter
    def cache(self, cache):
        os.environ[self.TMDB_CACHE_ENABLED] = str(cache)

    @staticmethod
    def _get_obj(result, key="results", all_details=False):
        if "success" in result and result["success"] is False:
            raise TMDbError(result["status_message"])
        if all_details is True or key is None:
            return AsObj(**result)
        else:
            return [AsObj(**res) for res in result[key]]

    @staticmethod
    @lru_cache(maxsize=REQUEST_CACHE_MAXSIZE)
    def cached_request(method, url, data, proxies):
        _proxies = json.loads(proxies) if isinstance(proxies, str) else (proxies or {})
        return requests.request(method, url, data=data, proxies=_proxies, verify=False, timeout=10)

    def cache_clear(self):
        return self.cached_request.cache_clear()

    def _call(self, action, append_to_response, call_cached=True, method="GET", data=None):
        if self.api_key is None or self.api_key == "":
            raise TMDbError("No API key found.")

        url = f"{self.domain}{action}?api_key={self.api_key}&include_adult=false&{append_to_response}&language={self.language}"

        def do_request():
            # 使用速率限制器控制请求频率
            rate_limiter = get_rate_limiter()
            if not rate_limiter.acquire(timeout=30):  # 最多等待30秒
                raise TMDbError("获取速率限制令牌超时")

            if self.cache and self.obj_cached and call_cached and method != "POST":
                req = self.cached_request(method, url, data, self.proxies)
            else:
                _proxies = json.loads(self.proxies) if isinstance(self.proxies, str) else (self.proxies or {})
                req = self._session.request(method, url, data=data, proxies=_proxies, timeout=10, verify=False)
            return req

        # 使用指数退避重试机制
        retry_handler = get_retry_handler()
        try:
            req = retry_handler.execute(do_request)
        except Exception as e:
            logger.error(f"[TMDB]请求失败，重试后仍失败: {str(e)}")
            raise

        if req is None:
            raise TMDbError("请求返回空响应")

        headers = req.headers

        if "X-RateLimit-Remaining" in headers:
            self._remaining = int(headers["X-RateLimit-Remaining"])

        if "X-RateLimit-Reset" in headers:
            self._reset = int(headers["X-RateLimit-Reset"])

        # 如果响应码是 429，说明被限流了，触发指数退避
        if req.status_code == 429:
            retry_after = int(headers.get("Retry-After", 1))
            logger.warning(f"[TMDB]收到 429 响应，等待 {retry_after} 秒后重试")
            time.sleep(retry_after)
            return self._call(action, append_to_response, call_cached, method, data)

        json = req.json()

        if "page" in json:
            os.environ["PAGE"] = str(json["page"])

        if "total_results" in json:
            os.environ["TOTAL_RESULTS"] = str(json["total_results"])

        if "total_pages" in json:
            os.environ["TOTAL_PAGES"] = str(json["total_pages"])

        if self.debug:
            logger.info(json)
            logger.info(self.cached_request.cache_info())

        if "errors" in json:
            raise TMDbError(json["errors"])

        return json

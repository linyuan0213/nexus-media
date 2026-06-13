"""TMDb API 核心 — 基于 HttpClient 重写."""

import os

from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.infrastructure.http.retry import HttpRetryConfig
from app.infrastructure.tmdb import get_rate_limiter
from app.utils.json_utils import JsonUtils

from .as_obj import AsObj
from .exceptions import TMDbError


def _parse_proxies(proxies: str | dict | None) -> str | None:
    """解析代理配置，返回 proxy_url 字符串."""
    if not proxies:
        return None
    parsed = JsonUtils.loads(proxies) if isinstance(proxies, str) else proxies
    return parsed.get("http") if isinstance(parsed, dict) else None


class TMDb:
    TMDB_API_KEY = "TMDB_API_KEY"
    TMDB_LANGUAGE = "TMDB_LANGUAGE"
    TMDB_PROXIES = "TMDB_PROXIES"
    TMDB_DOMAIN = "TMDB_DOMAIN"

    def __init__(self, session=None):
        self._session = session
        self._remaining = 40
        self._reset = None
        if os.environ.get(self.TMDB_LANGUAGE) is None:
            os.environ[self.TMDB_LANGUAGE] = "zh"
        if not os.environ.get(self.TMDB_DOMAIN):
            os.environ[self.TMDB_DOMAIN] = "https://api.themoviedb.org/3"

    def _get_client(self) -> HttpClient:
        """获取或创建带限流 + 重试的 HttpClient 实例."""
        if self._session is not None:
            return self._session
        proxy_url = _parse_proxies(self.proxies)
        return HttpClient(
            config=HttpClientConfig(proxy_url=proxy_url, timeout=10),
            retry_config=HttpRetryConfig(max_attempts=3, min_wait=1.0),
            rate_limiter=get_rate_limiter().engine,
        )

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

    @staticmethod
    def _get_obj(result, key="results", all_details=False):
        if "success" in result and result["success"] is False:
            raise TMDbError(result["status_message"])
        if all_details is True or key is None:
            return AsObj(**result)
        else:
            return [AsObj(**res) for res in result[key]]

    def _call(self, action, append_to_response, method="GET", data=None):
        if self.api_key is None or self.api_key == "":
            raise TMDbError("No API key found.")

        url = (
            f"{self.domain}{action}?api_key={self.api_key}"
            f"&include_adult=false&{append_to_response}&language={self.language}"
        )

        client = self._get_client()
        req = client.request(
            method,
            url,
            data=data,
            rate_limit_key="tmdb:api",
            rate_limit_rate="2.5/s",
        )

        headers = req.headers
        if "X-RateLimit-Remaining" in headers:
            self._remaining = int(headers["X-RateLimit-Remaining"])
        if "X-RateLimit-Reset" in headers:
            self._reset = int(headers["X-RateLimit-Reset"])

        json_data = req.json()

        if "page" in json_data:
            os.environ["PAGE"] = str(json_data["page"])
        if "total_results" in json_data:
            os.environ["TOTAL_RESULTS"] = str(json_data["total_results"])
        if "total_pages" in json_data:
            os.environ["TOTAL_PAGES"] = str(json_data["total_pages"])

        if "errors" in json_data:
            raise TMDbError(json_data["errors"])

        return json_data

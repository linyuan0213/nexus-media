"""Fanart API 图片获取模块.

修复前：单例 _images 缓存导致查询不同媒体时返回错误图片。
修复后：以 (media_type, queryid) 为 key 的缓存字典，每个媒体独立缓存。
"""

from app.core.constants import FANART_MOVIE_API_URL, FANART_TV_API_URL
from app.infrastructure.cache_system import lru_cache_with_ttl
from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.infrastructure.http.exceptions import HttpClientError
from app.utils import ExceptionUtils
from app.utils.config_tools import get_proxies
from app.domain.mediatypes import MediaType


class Fanart:
    _proxies = get_proxies()
    _movie_image_types = ["movieposter", "hdmovielogo", "moviebackground", "moviedisc", "moviebanner", "moviethumb"]
    _tv_image_types = [
        "hdtvlogo",
        "tvthumb",
        "showbackground",
        "tvbanner",
        "seasonposter",
        "seasonbanner",
        "seasonthumb",
        "tvposter",
        "hdclearart",
    ]
    _season_types = ["seasonposter", "seasonthumb", "seasonbanner"]

    def __init__(self):
        self._images: dict[str, dict] = {}

    def _cache_key(self, media_type, queryid) -> str:
        return f"{media_type.value if hasattr(media_type, 'value') else media_type}_{queryid}"

    def _get_images(self, media_type, queryid) -> dict:
        """获取指定媒体的图片缓存，不存在时请求 API."""
        key = self._cache_key(media_type, queryid)
        if key not in self._images:
            self._images[key] = self._fetch_fanart_images(media_type, queryid)
        return self._images.get(key, {})

    def _fetch_fanart_images(self, media_type, queryid) -> dict:
        if not media_type or not queryid:
            return {}
        images: dict = {}
        try:
            ret = self.__request_fanart(media_type=media_type, queryid=queryid)
            if not ret:
                return images
            data = ret.json()
            if media_type == MediaType.MOVIE:
                for image_type in self._movie_image_types:
                    items = data.get(image_type)
                    if isinstance(items, list) and items:
                        images[image_type] = items[0].get("url") if isinstance(items[0], dict) else ""
                    else:
                        images[image_type] = ""
            else:
                for image_type in self._tv_image_types:
                    items = data.get(image_type)
                    if isinstance(items, list):
                        if image_type in self._season_types:
                            images[image_type] = {}
                            for item in items:
                                season = item.get("season")
                                if season is not None and season not in images[image_type]:
                                    images[image_type][season] = item.get("url")
                        else:
                            images[image_type] = items[0].get("url") if isinstance(items[0], dict) else ""
                    else:
                        if image_type in self._season_types:
                            images[image_type] = {}
                        else:
                            images[image_type] = ""
        except Exception:
            ExceptionUtils.exception_traceback(Exception())
        return images

    @classmethod
    @lru_cache_with_ttl(maxsize=256, ttl=3600)
    def __request_fanart(cls, media_type, queryid):
        if media_type == MediaType.MOVIE:
            image_url = FANART_MOVIE_API_URL % queryid
        else:
            image_url = FANART_TV_API_URL % queryid
        proxy_url = cls._proxies.get("http") if cls._proxies else None
        try:
            return HttpClient(config=HttpClientConfig(proxy_url=proxy_url, timeout=5)).get(image_url)
        except HttpClientError as err:
            ExceptionUtils.exception_traceback(err)
        return None

    def get_backdrop(self, media_type, queryid, default=""):
        if not media_type or not queryid:
            return default
        images = self._get_images(media_type, queryid)
        key = "moviethumb" if media_type == MediaType.MOVIE else "tvthumb"
        return images.get(key, default)

    def get_poster(self, media_type, queryid, default=None):
        if not media_type or not queryid:
            return default
        images = self._get_images(media_type, queryid)
        key = "movieposter" if media_type == MediaType.MOVIE else "tvposter"
        return images.get(key, default)

    def get_background(self, media_type, queryid, default=None):
        if not media_type or not queryid:
            return default
        images = self._get_images(media_type, queryid)
        key = "moviebackground" if media_type == MediaType.MOVIE else "showbackground"
        return images.get(key, default)

    def get_banner(self, media_type, queryid, default=None):
        if not media_type or not queryid:
            return default
        images = self._get_images(media_type, queryid)
        key = "moviebanner" if media_type == MediaType.MOVIE else "tvbanner"
        return images.get(key, default)

    def get_disc(self, media_type, queryid, default=None):
        if not media_type or not queryid:
            return default
        if media_type != MediaType.MOVIE:
            return default
        images = self._get_images(media_type, queryid)
        return images.get("moviedisc", default)

    def get_logo(self, media_type, queryid, default=None):
        if not media_type or not queryid:
            return default
        images = self._get_images(media_type, queryid)
        key = "hdmovielogo" if media_type == MediaType.MOVIE else "hdtvlogo"
        return images.get(key, default)

    def get_thumb(self, media_type, queryid, default=None):
        if not media_type or not queryid:
            return default
        images = self._get_images(media_type, queryid)
        key = "moviethumb" if media_type == MediaType.MOVIE else "tvthumb"
        return images.get(key, default)

    def get_clearart(self, media_type, queryid, default=None):
        if not media_type or not queryid or media_type != MediaType.TV:
            return default
        images = self._get_images(media_type, queryid)
        return images.get("hdclearart", default)

    def get_seasonposter(self, media_type, queryid, season, default=None):
        if not media_type or not queryid or media_type != MediaType.TV:
            return default
        images = self._get_images(media_type, queryid)
        return images.get("seasonposter", {}).get(season, "") or default

    def get_seasonthumb(self, media_type, queryid, season, default=None):
        if not media_type or not queryid or media_type != MediaType.TV:
            return default
        images = self._get_images(media_type, queryid)
        return images.get("seasonthumb", {}).get(season, "") or default

    def get_seasonbanner(self, media_type, queryid, season, default=None):
        if not media_type or not queryid or media_type != MediaType.TV:
            return default
        images = self._get_images(media_type, queryid)
        return images.get("seasonbanner", {}).get(season, "") or default

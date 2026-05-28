import difflib

import zhconv

from app.core.settings import settings
from app.infrastructure.cache_system import TMDBCache, get_cache_manager
from app.infrastructure.external.tmdbv3api import (
    TV,
    Discover,
    Episode,
    Find,
    Genre,
    Movie,
    Person,
    Search,
    TMDb,
    Trending,
)
from app.utils import StringUtils
from app.utils.config_tools import get_proxies, get_tmdbapi_url
from app.utils.types import MediaType
from app.di import container


class TmdbClient:
    """TMDB API 客户端封装"""

    def __init__(self):
        self.tmdb = None
        self.search = None
        self.movie = None
        self.tv = None
        self.episode = None
        self.person = None
        self.find = None
        self.trending = None
        self.discover = None
        self.genre = None
        self._default_language = "zh"
        self._init_config()

    def _init_config(self):
        app = settings.get("app")
        media = settings.get("media")
        _lang = media.get("tmdb_language", "zh")
        self._default_language = _lang if isinstance(_lang, str) else "zh"
        _api_key = app.get("rmt_tmdbkey")
        if isinstance(_api_key, str) and _api_key:
            self.tmdb = TMDb()
            self.tmdb.domain = get_tmdbapi_url()
            self.tmdb.cache = True
            self.tmdb.api_key = _api_key
            self.tmdb.language = self._default_language
            self.tmdb.proxies = get_proxies()
            self.tmdb.debug = False
            self.search = Search()
            self.movie = Movie()
            self.tv = TV()
            self.episode = Episode()
            self.find = Find()
            self.person = Person()
            self.trending = Trending()
            self.discover = Discover()
            self.genre = Genre()
        self.redis_cache = TMDBCache(get_cache_manager().get("tmdb"))
        self.blacklist = container.tmdb_blacklist_repo()
        self._blacklist_cache = get_cache_manager().get_or_create("tmdb_blacklist", "memory", maxsize=1, ttl=300)

    def get_blacklist(self):
        cached = self._blacklist_cache.get("all")
        if cached is not None:
            return cached
        all_items = self.blacklist.get_tmdb_blacklist()
        self._blacklist_cache.set("all", all_items)
        return all_items

    def set_language(self, language: str = ""):
        if not self.tmdb:
            return
        if language:
            self.tmdb.language = language
        else:
            self.tmdb.language = self._default_language


# ---------- 纯工具函数 ----------


def compare_tmdb_names(file_name, tmdb_names):
    if not file_name or not tmdb_names:
        return False
    if not isinstance(tmdb_names, list):
        tmdb_names = [tmdb_names]
    _fn = StringUtils.handler_special_chars(str(file_name))
    file_name = _fn.upper() if isinstance(_fn, str) else str(file_name).upper()
    for tmdb_name in tmdb_names:
        _tn = StringUtils.handler_special_chars(str(tmdb_name))
        tmdb_name = _tn.strip().upper() if isinstance(_tn, str) else str(tmdb_name).strip().upper()
        if file_name == tmdb_name:
            return True
        if len(file_name) < 3 or len(tmdb_name) < 3:
            continue
        # 子串关系（如 "海贼王" vs "海贼王女"）→ 要求更高相似度，避免短名误匹配
        is_substring = file_name in tmdb_name or tmdb_name in file_name
        ratio = difflib.SequenceMatcher(None, file_name, tmdb_name).ratio()
        threshold = 0.95 if is_substring else 0.75
        if ratio >= threshold:
            return True
    return False


def get_genre_ids_from_detail(genres):
    if not genres:
        return []
    return [genre.get("id") for genre in genres]


def get_tmdb_chinese_title(tmdbinfo):
    if not tmdbinfo:
        return None
    if tmdbinfo.get("media_type") == MediaType.MOVIE:
        alternative_titles = tmdbinfo.get("alternative_titles", {}).get("titles", [])
    else:
        alternative_titles = tmdbinfo.get("alternative_titles", {}).get("results", [])
    for alternative_title in alternative_titles:
        iso_3166_1 = alternative_title.get("iso_3166_1")
        if iso_3166_1 == "CN":
            title = alternative_title.get("title")
            if title and StringUtils.is_chinese(title) and zhconv.convert(title, "zh-hans") == title:
                return title
    return tmdbinfo.get("title") if tmdbinfo.get("media_type") == MediaType.MOVIE else tmdbinfo.get("name")


def update_tmdbinfo_cn_title(tmdb_info, default_language):
    org_title = tmdb_info.get("title") if tmdb_info.get("media_type") == MediaType.MOVIE else tmdb_info.get("name")
    if not StringUtils.is_chinese(org_title) and default_language == "zh":
        cn_title = get_tmdb_chinese_title(tmdbinfo=tmdb_info)
        if cn_title and cn_title != org_title:
            if tmdb_info.get("media_type") == MediaType.MOVIE:
                tmdb_info["title"] = cn_title
            else:
                tmdb_info["name"] = cn_title
    return tmdb_info

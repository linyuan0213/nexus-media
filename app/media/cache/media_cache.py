from typing import Any, Optional

from app.media.models import MediaInfo
from app.infrastructure.cache_system import TMDBCache, get_cache_manager
from app.utils.types import MediaType


class MediaCache:
    """媒体缓存门面 — 统一提供 TMDB 详情查询"""

    def __init__(self):
        self._tmdb_cache = TMDBCache(get_cache_manager().get("tmdb"))

    def get_tmdb_info(self, mtype: MediaType, tmdbid, language: str = None) -> Optional[dict]:
        """已知 tmdb_id 查 TMDB 详情（优先缓存）"""
        if not tmdbid:
            return None
        return self._tmdb_cache.get_tmdb_info(mtype, str(tmdbid), language)

    def set_tmdb_info(self, mtype: MediaType, tmdbid, info: dict, language: str = None):
        """缓存 TMDB 详情"""
        if not tmdbid or not info:
            return
        self._tmdb_cache.set_tmdb_info(mtype, str(tmdbid), info, language)

    def get_media_info(self, title: str, year: str = None, mtype: MediaType = None) -> Optional[MediaInfo]:
        """获取识别结果缓存（如有需要可扩展）"""
        return None

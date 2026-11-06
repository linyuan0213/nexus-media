from app.domain.mediatypes import MediaType
from app.infrastructure.cache_system.metadata_cache import MetadataCache
from app.media.models import MediaInfo


class MediaCache:
    """媒体缓存门面 — 统一提供 TMDB 详情查询"""

    def __init__(self):
        self._metadata_cache = MetadataCache()

    def get_tmdb_info(self, mtype: MediaType, tmdbid, language: str | None = None) -> dict | None:
        """已知 tmdb_id 查 TMDB 详情（优先缓存）"""
        if not tmdbid or not str(tmdbid).isdigit():
            return None
        return self._metadata_cache.get_detail("tmdb", str(tmdbid), mtype, language=language)

    def set_provider_data(self, mtype: MediaType, tmdbid, info: dict, language: str | None = None):
        """缓存 TMDB 详情"""
        if not tmdbid or not info:
            return
        self._metadata_cache.set_detail("tmdb", str(tmdbid), info, mtype, language=language)

    def get_media_info(self, title: str, year: str | None = None, mtype: MediaType | None = None) -> MediaInfo | None:
        """获取识别结果缓存（如有需要可扩展）"""
        return None

from app.media.cache import MediaCache
from app.media.service import MediaService
from app.di import container

_media_service = None
_media_cache = None


def get_media_service() -> MediaService:
    """获取 MediaService 单例 — 用于文件名识别"""
    global _media_service
    if _media_service is None:
        _media_service = MediaService()
    return _media_service


def get_media_cache() -> MediaCache:
    """获取 MediaCache 单例 — 用于已知 tmdb_id 查详情"""
    global _media_cache
    if _media_cache is None:
        _media_cache = container.media_cache()
    return _media_cache

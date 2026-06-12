from app.media.cache import MediaCache

_media_cache = None


def get_media_cache(media_cache: MediaCache | None = None) -> MediaCache:
    """获取 MediaCache 单例 — 用于已知 tmdb_id 查详情"""
    global _media_cache
    if _media_cache is None:
        _media_cache = media_cache or MediaCache()
    return _media_cache

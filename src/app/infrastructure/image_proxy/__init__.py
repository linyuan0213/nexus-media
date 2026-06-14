"""图片代理与缓存."""

from app.infrastructure.image_proxy.core import (
    MAX_CACHE_DAYS,
    SIZE_DIMENSIONS,
    SOURCE_DOMAINS,
    clean_old_cache,
    download_image,
    get_cache_path,
    resize_image,
)
from app.infrastructure.image_proxy.proxy import ImageProxy

__all__ = [
    "ImageProxy",
    "MAX_CACHE_DAYS",
    "SIZE_DIMENSIONS",
    "SOURCE_DOMAINS",
    "clean_old_cache",
    "download_image",
    "get_cache_path",
    "resize_image",
]

"""媒体类型映射工具"""

from app.utils.types import MediaType


class MediaTypeMapper:
    """媒体类型映射器 — 统一管理类型转换"""

    TMDB_MAP: dict[str, MediaType] = {
        "movie": MediaType.MOVIE,
        "tv": MediaType.TV,
    }

    SITE_CAT_MAP: dict[str, dict[str, MediaType]] = {
        "default": {
            "movie": MediaType.MOVIE,
            "tv": MediaType.TV,
            "anime": MediaType.ANIME,
        },
    }

    @classmethod
    def from_tmdb(cls, tmdb_type: str) -> MediaType:
        """从 TMDB 类型字符串转枚举"""
        return cls.TMDB_MAP.get(tmdb_type.lower(), MediaType.UNKNOWN)

    @classmethod
    def to_tmdb(cls, media_type: MediaType) -> str:
        """从枚举转 TMDB 类型字符串"""
        if media_type == MediaType.MOVIE:
            return "movie"
        if media_type in (MediaType.TV, MediaType.ANIME):
            return "tv"
        return ""

    @classmethod
    def from_site_cat(cls, cat: str, site: str = "default") -> MediaType:
        """从站点分类编码转枚举"""
        site_map = cls.SITE_CAT_MAP.get(site, cls.SITE_CAT_MAP["default"])
        return site_map.get(cat.lower(), MediaType.UNKNOWN)

    @classmethod
    def to_site_cat(cls, media_type: MediaType, site: str = "default") -> str:
        """从枚举转站点分类编码"""
        site_map = cls.SITE_CAT_MAP.get(site, cls.SITE_CAT_MAP["default"])
        for cat, mt in site_map.items():
            if mt == media_type:
                return cat
        return ""

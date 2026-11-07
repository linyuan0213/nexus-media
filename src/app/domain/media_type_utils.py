"""媒体类型映射工具"""

from app.domain.media_types import ProviderMediaType


class ProviderMediaTypeMapper:
    """媒体类型映射器 — 统一管理类型转换"""

    TMDB_MAP: dict[str, ProviderMediaType] = {
        "movie": ProviderMediaType.MOVIE,
        "tv": ProviderMediaType.SERIES,
    }

    SITE_CAT_MAP: dict[str, dict[str, ProviderMediaType]] = {
        "default": {
            "movie": ProviderMediaType.MOVIE,
            "tv": ProviderMediaType.SERIES,
            "anime": ProviderMediaType.ANIME,
        },
    }

    @classmethod
    def from_tmdb(cls, tmdb_type: str) -> ProviderMediaType:
        """从 TMDB 类型字符串转枚举"""
        return cls.TMDB_MAP.get(tmdb_type.lower(), ProviderMediaType.UNKNOWN)

    @classmethod
    def to_tmdb(cls, media_type: ProviderMediaType) -> str:
        """从枚举转 TMDB 类型字符串"""
        if media_type == ProviderMediaType.MOVIE:
            return "movie"
        if media_type in (ProviderMediaType.SERIES, ProviderMediaType.ANIME):
            return "tv"
        return ""

    @classmethod
    def from_site_cat(cls, cat: str, site: str = "default") -> ProviderMediaType:
        """从站点分类编码转枚举"""
        site_map = cls.SITE_CAT_MAP.get(site, cls.SITE_CAT_MAP["default"])
        return site_map.get(cat.lower(), ProviderMediaType.UNKNOWN)

    @classmethod
    def to_site_cat(cls, media_type: ProviderMediaType, site: str = "default") -> str:
        """从枚举转站点分类编码"""
        site_map = cls.SITE_CAT_MAP.get(site, cls.SITE_CAT_MAP["default"])
        for cat, mt in site_map.items():
            if mt == media_type:
                return cat
        return ""

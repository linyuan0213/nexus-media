"""app.media — 媒体处理模块

重构后架构:
  - MediaService     — 文件名识别门面
  - MediaCache       — TMDB 详情缓存
  - MediaInfo        — pydantic 数据模型
  - parser/          — 文件名解析层
  - lookup/          — 外部数据库查询层
  - scraper/         — 元数据刮削层（NFO / 图片）
  - external/        — 第三方 API 客户端（豆瓣、Bangumi）
  - batch/           — 批量处理
  - cache/           — 缓存层
"""

from .models import MediaInfo
from .parser import (
    AnitopyAdapter,
    BaseParser,
    LLMParser,
    ParserResult,
    RegexParser,
    TokenAdapter,
)
from .lookup import (
    BaseLookup,
    BangumiLookup,
    DoubanLookup,
    LookupResult,
    TmdbLookup,
)
from .batch import BatchProcessor
from .cache import MediaCache
from .service import MediaService
from .factory import get_media_cache, get_media_service
from .category import Category
from .scraper import Scraper
from .external import DouBan, Bangumi
from .parser._metainfo import MetaInfo
from .parser._release_groups import ReleaseGroupsMatcher
from .parser._customization import CustomizationMatcher


__all__ = [
    "MediaService",
    "MediaCache",
    "MediaInfo",
    "BatchProcessor",
    "BaseParser",
    "ParserResult",
    "RegexParser",
    "LLMParser",
    "AnitopyAdapter",
    "TokenAdapter",
    "BaseLookup",
    "LookupResult",
    "TmdbLookup",
    "DoubanLookup",
    "BangumiLookup",
    "Category",
    "DouBan",
    "Bangumi",
    "Scraper",
]

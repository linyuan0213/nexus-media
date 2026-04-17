from .dom_utils import DomUtils
from .episode_format import EpisodeFormat
from .http_utils import RequestUtils
from .json_utils import JsonUtils
from .number_utils import NumberUtils
from .path_utils import PathUtils
from .string_utils import StringUtils
from .system_utils import SystemUtils
from .tokens import Tokens
from .torrent import Torrent
from .exception_utils import ExceptionUtils
from .rsstitle_utils import RssTitleUtils
from .nfo_reader import NfoReader
from .ip_utils import IpUtils
from .image_utils import ImageUtils
from .redis_store import RedisStore
from .temp_manager import TempManager, temp_manager, temp_file_context, temp_dir_context

# 新的统一缓存系统
from .cache_system import (
    CacheManager,
    MemoryCacheAdapter,
    RedisCacheAdapter,
    TMDBCache,
    MediaInfoCache,
    SearchResultCache,
    TokenCache,
    ConfigLoadCache,
    CategoryLoadCache,
    OpenAISessionCache,
    SiteInfoCache,
    cached,
    cached_with_lock,
    lru_cache_with_ttl,
    CacheKeyBuilder,
    get_cache_manager,
    CacheWarmer,
    ConfigCacheWarmer,
    SiteCacheWarmer,
    WordsCacheWarmer,
    TMDBTrendingWarmer,
    CacheWarmerManager,
    get_warmer_manager,
    warm_cache_on_startup,
)

# 兼容旧的缓存接口
from .cache_system.compat import cacheman

# 初始化全局缓存管理器并创建默认缓存
_cache_manager = get_cache_manager()
_cache_manager.create_memory_cache("tmdb_supply", maxsize=500)
_cache_manager.create_memory_cache("media_info", maxsize=1000)
_cache_manager.create_memory_cache("search_result", maxsize=500)
_cache_manager.create_memory_cache("token", maxsize=512)
_cache_manager.create_memory_cache("config_load", maxsize=1)
_cache_manager.create_memory_cache("category_load", maxsize=2)
_cache_manager.create_memory_cache("openai_session", maxsize=200)
_cache_manager.create_memory_cache("site_info", maxsize=100)
_cache_manager.create_redis_cache("tmdb")

# 创建专用缓存实例
MediaInfoCache = MediaInfoCache(_cache_manager.get("media_info"))
SearchResultCache = SearchResultCache(_cache_manager.get("search_result"))
SiteInfoCache = SiteInfoCache(_cache_manager.get("site_info"))
TokenCache = TokenCache(_cache_manager.get("token"))
ConfigLoadCache = ConfigLoadCache(_cache_manager.get("config_load"))
CategoryLoadCache = CategoryLoadCache(_cache_manager.get("category_load"))
OpenAISessionCache = OpenAISessionCache(_cache_manager.get("openai_session"))

__all__ = [
    # 原有工具
    'DomUtils',
    'EpisodeFormat',
    'RequestUtils',
    'JsonUtils',
    'NumberUtils',
    'PathUtils',
    'StringUtils',
    'SystemUtils',
    'Tokens',
    'Torrent',
    'ExceptionUtils',
    'RssTitleUtils',
    'NfoReader',
    'IpUtils',
    'ImageUtils',
    'RedisStore',
    'TempManager',
    'temp_manager',
    'temp_file_context',
    'temp_dir_context',
    # 新的缓存系统
    'CacheManager',
    'MemoryCacheAdapter',
    'RedisCacheAdapter',
    'TMDBCache',
    'MediaInfoCache',
    'SearchResultCache',
    'TokenCache',
    'ConfigLoadCache',
    'CategoryLoadCache',
    'OpenAISessionCache',
    'SiteInfoCache',
    'cached',
    'cached_with_lock',
    'lru_cache_with_ttl',
    'CacheKeyBuilder',
    'get_cache_manager',
    # 缓存预热
    'CacheWarmer',
    'ConfigCacheWarmer',
    'SiteCacheWarmer',
    'WordsCacheWarmer',
    'TMDBTrendingWarmer',
    'CacheWarmerManager',
    'get_warmer_manager',
    'warm_cache_on_startup',
    # 兼容旧接口
    'cacheman',
]

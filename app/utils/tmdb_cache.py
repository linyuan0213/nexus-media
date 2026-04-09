import log
import pickle
from typing import Optional, Dict, Any
from app.utils.redis_store import RedisStore
from app.utils.types import MediaType

class TMDBCache:
    """
    TMDB 缓存管理器
    
    缓存策略：
    - TMDB 信息（电影/电视剧详情）：缓存 7 天（不常变化）
    - 媒体信息（搜索结果）：缓存 24 小时
    - 季集信息：缓存 12 小时（可能更新）
    - 演员信息：缓存 30 天
    - 热门/趋势列表：缓存 2 小时（经常变化）
    """
    
    # 不同数据类型的 TTL（秒）
    TTL_TMDB_INFO = 7 * 24 * 3600      # 7 天
    TTL_MEDIA_INFO = 24 * 3600          # 24 小时
    TTL_SEASON_INFO = 12 * 3600         # 12 小时
    TTL_PERSON_INFO = 30 * 24 * 3600    # 30 天
    TTL_TRENDING = 2 * 3600             # 2 小时
    TTL_DEFAULT = 3600                  # 1 小时（默认）
    
    def __init__(self):
        self.redis = RedisStore()

    def get_tmdb_info(self, mtype: MediaType, tmdbid: str, language: str = None) -> Optional[Any]:
        """从缓存获取TMDB信息，支持字典和对象"""
        if mtype == MediaType.ANIME:
            mtype = MediaType.TV
        cache_key = f"tmdb:{mtype.value}:{tmdbid}:{language or 'default'}"
        cached = self.redis.get(cache_key)
        if cached:
            try:
                result = pickle.loads(cached)
                log.debug(f"从Redis缓存命中TMDB信息: {cache_key}")
                return result
            except:
                log.debug(f"从Redis缓存命中TMDB信息(原始值): {cache_key}")
                return cached
        return None

    def set_tmdb_info(self, mtype: MediaType, tmdbid: str, info: Any,
                     language: str = None, ttl: int = None) -> None:
        """缓存TMDB信息，支持字典和对象，默认7天"""
        if mtype == MediaType.ANIME:
            mtype = MediaType.TV
        
        # 使用默认 TTL 如果未指定
        if ttl is None:
            ttl = self.TTL_TMDB_INFO

        cache_key = f"tmdb:{mtype.value}:{tmdbid}:{language or 'default'}"
        # 其他类型则序列化存储
        value = pickle.dumps(info)
        self.redis.set(cache_key, value, ex=ttl)
        log.debug(f"已缓存TMDB信息到Redis: {cache_key}, TTL={ttl}秒")

    def get_media_info(self, title: str, year: str = None, 
                      mtype: MediaType = None) -> Optional[Any]:
        """从缓存获取媒体信息，支持字典和对象"""
        if mtype == MediaType.ANIME:
            mtype = MediaType.TV
        cache_key = self._get_media_cache_key(title, year, mtype)
        cached = self.redis.get(cache_key)
        if cached:
            try:
                # 尝试反序列化对象
                result = pickle.loads(cached)
                log.debug(f"从Redis缓存命中媒体信息: {cache_key}")
                return result
            except:
                # 如果反序列化失败，直接返回原始值(兼容旧字典数据)
                log.debug(f"从Redis缓存命中媒体信息(原始值): {cache_key}")
                return cached
        return None

    def set_media_info(self, title: str, info: Any,
                      year: str = None, mtype: MediaType = None,
                      ttl: int = None) -> None:
        """缓存媒体信息（搜索结果），支持字典和对象，默认24小时"""
        if mtype == MediaType.ANIME:
            mtype = MediaType.TV
        if ttl is None:
            ttl = self.TTL_MEDIA_INFO
        cache_key = self._get_media_cache_key(title, year, mtype)
        value = pickle.dumps(info)
        self.redis.set(cache_key, value, ex=ttl)
        log.debug(f"已缓存媒体信息到Redis: {cache_key}, TTL={ttl}秒")

    def get_season_info(self, tmdbid: str, season: int) -> Optional[Any]:
        """获取季详情缓存"""
        cache_key = f"tmdb:season:{tmdbid}:{season}"
        cached = self.redis.get(cache_key)
        if cached:
            try:
                return pickle.loads(cached)
            except:
                return cached
        return None

    def set_season_info(self, tmdbid: str, season: int, info: Any, ttl: int = None) -> None:
        """缓存季详情，默认12小时"""
        if ttl is None:
            ttl = self.TTL_SEASON_INFO
        cache_key = f"tmdb:season:{tmdbid}:{season}"
        value = pickle.dumps(info)
        self.redis.set(cache_key, value, ex=ttl)
        log.debug(f"已缓存季详情到Redis: {cache_key}, TTL={ttl}秒")

    def get_person_info(self, person_id: str) -> Optional[Any]:
        """获取演员信息缓存"""
        cache_key = f"tmdb:person:{person_id}"
        cached = self.redis.get(cache_key)
        if cached:
            try:
                return pickle.loads(cached)
            except:
                return cached
        return None

    def set_person_info(self, person_id: str, info: Any, ttl: int = None) -> None:
        """缓存演员信息，默认30天"""
        if ttl is None:
            ttl = self.TTL_PERSON_INFO
        cache_key = f"tmdb:person:{person_id}"
        value = pickle.dumps(info)
        self.redis.set(cache_key, value, ex=ttl)
        log.debug(f"已缓存演员信息到Redis: {cache_key}, TTL={ttl}秒")

    def get_trending(self, media_type: str, time_window: str, page: int = 1) -> Optional[Any]:
        """获取热门趋势缓存"""
        cache_key = f"tmdb:trending:{media_type}:{time_window}:{page}"
        cached = self.redis.get(cache_key)
        if cached:
            try:
                return pickle.loads(cached)
            except:
                return cached
        return None

    def set_trending(self, media_type: str, time_window: str, page: int, info: Any, ttl: int = None) -> None:
        """缓存热门趋势，默认2小时"""
        if ttl is None:
            ttl = self.TTL_TRENDING
        cache_key = f"tmdb:trending:{media_type}:{time_window}:{page}"
        value = pickle.dumps(info)
        self.redis.set(cache_key, value, ex=ttl)
        log.debug(f"已缓存趋势信息到Redis: {cache_key}, TTL={ttl}秒")

    def _get_media_cache_key(self, title: str, year: str = None,
                            mtype: MediaType = None) -> str:
        """生成媒体信息缓存键"""
        parts = ["media", title]
        if year:
            parts.append(year)
        if mtype:
            parts.append(mtype.value)
        return ":".join(parts)

    def clear_tmdb_cache(self, tmdbid: str) -> None:
        """清除指定TMDB ID的所有缓存"""
        pattern = f"tmdb:*:{tmdbid}:*"
        keys = self.redis.keys(pattern)
        if keys:
            self.redis.delete(*keys)
            log.debug(f"已清除TMDB ID {tmdbid} 的所有缓存")

    def clear_media_cache(self, title: str) -> None:
        """清除指定标题的所有媒体缓存"""
        pattern = f"media:{title}:*"
        keys = self.redis.keys(pattern)
        if keys:
            self.redis.delete(*keys)
            log.debug(f"已清除标题 {title} 的所有媒体缓存")

    def get_cache_stats(self) -> dict:
        """获取缓存统计信息"""
        patterns = {
            "tmdb_info": "tmdb:movie:*",
            "tmdb_tv_info": "tmdb:tv:*",
            "media_info": "media:*",
            "season_info": "tmdb:season:*",
            "person_info": "tmdb:person:*",
            "trending": "tmdb:trending:*"
        }
        stats = {}
        for name, pattern in patterns.items():
            keys = self.redis.keys(pattern)
            stats[name] = len(keys)
        return stats

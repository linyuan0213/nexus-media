from app.db.repositories.plugin_repo_adapter import TmdbBlacklistRepositoryAdapter
from app.infrastructure.cache_system import get_cache_manager
from app.media import MediaService
from app.media.parser._metainfo import MetaInfo
from app.utils.types import MediaType


class TmdbBlacklistService:
    def __init__(self):
        self._db = TmdbBlacklistRepositoryAdapter()
        self._media = MediaService()
        self._cache = get_cache_manager().get_or_create("tmdb_blacklist", "memory", maxsize=1, ttl=300)

    def is_blacklisted(self, tmdb_id, media_type=None):
        """
        检查TMDB ID是否在黑名单中
        :param tmdb_id: TMDB ID
        :param media_type: 媒体类型
        :return: bool
        """
        return self._db.is_tmdb_blacklisted(tmdb_id, media_type)

    def _get_cached_all_items(self):
        """带缓存的获取全部黑名单记录"""
        cached = self._cache.get("all")
        if cached is not None:
            return cached
        all_items = self._db.get_tmdb_blacklist()
        self._cache.set("all", all_items)
        return all_items

    def get_blacklist(self, tmdb_id=None, page=1, count=30):
        """
        获取分页的黑名单记录
        :param page: 页码
        :param count: 每页数量
        :param tmdb_id: 按TMDB ID过滤
        :return: (当前页记录, 总记录数)
        """
        all_items = self._get_cached_all_items()
        if tmdb_id:
            all_items = [item for item in all_items if str(item.TMDB_ID) == str(tmdb_id)]

        start = (page - 1) * count
        end = start + count
        items = all_items[start:end]
        formatted_items = []
        for item in items:
            formatted_items.append(
                {
                    "backdrop_path": item.BACKDROP_PATH,
                    "id": item.ID,
                    "media_type": "电影" if MediaType.MOVIE.value == item.MEDIA_TYPE else "电视剧",
                    "note": item.NOTE,
                    "poster_path": item.POSTER_PATH,
                    "title": item.TITLE,
                    "tmdb_id": str(item.TMDB_ID),
                    "year": item.YEAR,
                }
            )
        return formatted_items, len(all_items)

    def add_to_blacklist(self, tmdb_id, media_type=""):
        """
        添加到黑名单
        :param tmdb_id: TMDB ID
        :param media_type: 媒体类型
        """
        if media_type == "电视剧":
            mtype = MediaType.TV
        elif media_type == "电影":
            mtype = MediaType.MOVIE
        else:
            mtype = MediaType.UNKNOWN

        tmdb_info = self._media.get_tmdb_info(mtype=mtype, tmdbid=tmdb_id)
        if not tmdb_info:
            raise ValueError(f"TMDB 信息获取失败：tmdb_id={tmdb_id}, type={media_type}")
        meta_info = MetaInfo(tmdb_info.get("name") or tmdb_info.get("title"))
        meta_info.set_tmdb_info(tmdb_info)
        self._db.insert_tmdb_blacklist(
            tmdb_id=tmdb_id,
            title=meta_info.title,
            year=meta_info.year,
            media_type=media_type,
            poster_path=meta_info.poster_path,
            backdrop_path=meta_info.backdrop_path,
            note=str(meta_info.note),
        )
        # 添加后清除缓存，确保下次查询能获取最新数据
        self._cache.clear()

    def remove_from_blacklist(self, tmdb_id, media_type=None):
        """
        从黑名单移除
        :param tmdb_id: TMDB ID
        :param media_type: 媒体类型
        """
        self._db.delete_tmdb_blacklist(tmdb_id, media_type)
        self._cache.clear()

    def clear_blacklist(self):
        """
        清空所有黑名单记录
        """
        self._db.clear_tmdb_blacklist()
        self._cache.clear()

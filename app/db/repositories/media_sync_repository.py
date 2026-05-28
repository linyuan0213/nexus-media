"""
媒体同步 Repository
处理媒体库同步相关的数据库操作
"""

import json
import time

from app.db import DbPersist
from app.db.models import MEDIASYNCITEMS, MEDIASYNCSTATISTIC
from app.db.repositories.base_repository import BaseRepository


class MediaSyncRepository(BaseRepository):
    """
    媒体同步数据仓储
    处理 MEDIASYNCITEMS 和 MEDIASYNCSTATISTIC 的数据库操作
    """

    @DbPersist(BaseRepository._db)
    def insert_item(self, server_type: str, iteminfo: dict, seasoninfo: list | None = None) -> bool:
        """
        插入/更新媒体同步项目
        """
        if not server_type or not iteminfo:
            return False

        self._db.query(MEDIASYNCITEMS).filter(
            MEDIASYNCITEMS.SERVER == server_type,
            MEDIASYNCITEMS.ITEM_ID == iteminfo.get("id"),
        ).delete()

        new_item = MEDIASYNCITEMS(
            SERVER=server_type,
            LIBRARY=iteminfo.get("library"),
            ITEM_ID=iteminfo.get("id"),
            ITEM_TYPE=iteminfo.get("type"),
            TITLE=iteminfo.get("title"),
            ORGIN_TITLE=iteminfo.get("originalTitle"),
            YEAR=iteminfo.get("year"),
            TMDBID=iteminfo.get("tmdbid"),
            IMDBID=iteminfo.get("imdbid"),
            PATH=iteminfo.get("path"),
            JSON=json.dumps(seasoninfo) if seasoninfo else None,
        )
        self._db.insert(new_item)
        return True

    @DbPersist(BaseRepository._db)
    def empty_items(self, server_type: str | None = None, library: str | None = None) -> bool:
        """
        清空媒体同步项目
        """
        query = self._db.query(MEDIASYNCITEMS)
        if server_type and library:
            query = query.filter(
                MEDIASYNCITEMS.SERVER == server_type,
                MEDIASYNCITEMS.LIBRARY == library,
            )
        elif server_type:
            query = query.filter(MEDIASYNCITEMS.SERVER == server_type)
        query.delete()
        return True

    @DbPersist(BaseRepository._db)
    def save_statistics(self, server_type: str, total_count: int, movie_count: int, tv_count: int) -> bool:
        """
        保存媒体同步统计
        """
        if not server_type:
            return False

        self._db.query(MEDIASYNCSTATISTIC).filter(MEDIASYNCSTATISTIC.SERVER == server_type).delete()

        new_stat = MEDIASYNCSTATISTIC(
            SERVER=server_type,
            TOTAL_COUNT=str(total_count),
            MOVIE_COUNT=str(movie_count),
            TV_COUNT=str(tv_count),
            UPDATE_TIME=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        )
        self._db.insert(new_stat)
        return True

    def query_item(self, server_type: str, title: str, year: str | None = None, tmdbid: str | None = None):
        """
        查询媒体同步项目
        """
        if not server_type or not title:
            return None

        query = self._db.query(MEDIASYNCITEMS).filter(MEDIASYNCITEMS.SERVER == server_type)

        if tmdbid:
            item = query.filter(MEDIASYNCITEMS.TMDBID == tmdbid).first()
            if item:
                return item

        if year:
            item = query.filter(
                MEDIASYNCITEMS.TITLE == title,
                MEDIASYNCITEMS.YEAR == year,
            ).first()
        else:
            item = query.filter(MEDIASYNCITEMS.TITLE == title).first()

        return item

    def get_statistics(self, server_type: str):
        """
        获取媒体同步统计
        """
        if not server_type:
            return None
        return self._db.query(MEDIASYNCSTATISTIC).filter(MEDIASYNCSTATISTIC.SERVER == server_type).first()

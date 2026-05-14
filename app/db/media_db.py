import json
import time

from app.db.main_db import SessionManager
from app.db.models import MEDIASYNCITEMS, MEDIASYNCSTATISTIC
from app.infrastructure.cache_system import MemoryCacheAdapter, cached
from app.utils import ExceptionUtils

# 创建媒体DB查询缓存
_media_db_cache = MemoryCacheAdapter(maxsize=128, name="media_db")


class MediaDb:
    """
    媒体数据库类
    使用 SessionManager 管理 session 生命周期
    """

    def __init__(self):
        self._sm = SessionManager()

    @property
    def session(self):
        return self._sm.session

    @staticmethod
    def init_db():
        """初始化数据库（由 MainDb.init_db() 统一创建所有表）"""

    def _close_session(self, session=None):
        """安全关闭 Session 并清理 scoped_session"""
        try:
            if session:
                session.close()
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
        finally:
            self._sm.remove()

    def insert(self, server_type, iteminfo, seasoninfo):
        if not server_type or not iteminfo:
            return False
        sess = self.session
        try:
            # 删除旧记录
            sess.query(MEDIASYNCITEMS).filter(
                server_type == MEDIASYNCITEMS.SERVER,
                iteminfo.get("id") == MEDIASYNCITEMS.ITEM_ID
            ).delete()
            # 插入新记录
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
                JSON=json.dumps(seasoninfo)
            )
            sess.add(new_item)
            sess.commit()
            return True
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            sess.rollback()
            return False
        finally:
            self._close_session(sess)

    def empty(self, server_type=None, library=None):
        sess = self.session
        try:
            query = sess.query(MEDIASYNCITEMS)
            if server_type and library:
                query = query.filter(server_type == MEDIASYNCITEMS.SERVER, library == MEDIASYNCITEMS.LIBRARY)
            elif server_type:
                query = query.filter(server_type == MEDIASYNCITEMS.SERVER)
            query.delete()
            sess.commit()
            return True
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            sess.rollback()
            return False
        finally:
            self._close_session(sess)

    def statistics(self, server_type, total_count, movie_count, tv_count):
        if not server_type:
            return False
        sess = self.session
        try:
            # 删除旧统计
            sess.query(MEDIASYNCSTATISTIC).filter(
                server_type == MEDIASYNCSTATISTIC.SERVER
            ).delete()
            # 插入新统计
            new_stat = MEDIASYNCSTATISTIC(
                SERVER=server_type,
                TOTAL_COUNT=total_count,
                MOVIE_COUNT=movie_count,
                TV_COUNT=tv_count,
                UPDATE_TIME=time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            )
            sess.add(new_stat)
            sess.commit()
            return True
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            sess.rollback()
            return False
        finally:
            self._close_session(sess)

    @cached(cache_instance=_media_db_cache, ttl=60)
    def query(self, server_type, title, year, tmdbid):
        sess = self.session
        try:
            if not server_type or not title:
                return {}

            query = sess.query(MEDIASYNCITEMS).filter(
                server_type == MEDIASYNCITEMS.SERVER
            )

            if tmdbid:
                item = query.filter(tmdbid == MEDIASYNCITEMS.TMDBID).first()
                if item:
                    return item

            if year:
                item = query.filter(
                    title == MEDIASYNCITEMS.TITLE,
                    year == MEDIASYNCITEMS.YEAR
                ).first()
            else:
                item = query.filter(title == MEDIASYNCITEMS.TITLE).first()

            return item if item else {}
        finally:
            self._close_session(sess)

    def get_statistics(self, server_type):
        sess = self.session
        try:
            if not server_type:
                return None
            return sess.query(MEDIASYNCSTATISTIC).filter(
                server_type == MEDIASYNCSTATISTIC.SERVER
            ).first()
        finally:
            self._close_session(sess)

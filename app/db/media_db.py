import json
import time

from cachetools import cached, TTLCache

from app.db.main_db import MainDb, _Engine, _Session
from app.db.models import MEDIASYNCITEMS, MEDIASYNCSTATISTIC
from app.utils import ExceptionUtils


class MediaDb:
    """
    媒体数据库类
    现在使用与主数据库相同的连接
    """
    
    @property
    def session(self):
        return _Session()

    @staticmethod
    def init_db():
        """初始化数据库（现在与主数据库共用）"""
        # 媒体表现在与主表在同一个数据库中
        # 由 MainDb.init_db() 统一创建所有表
        pass

    def _close_session(self):
        """安全关闭 Session 并清理 scoped_session"""
        try:
            self.session.close()
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
        finally:
            _Session.remove()

    def insert(self, server_type, iteminfo, seasoninfo):
        if not server_type or not iteminfo:
            return False
        try:
            # 删除旧记录
            self.session.query(MEDIASYNCITEMS).filter(
                MEDIASYNCITEMS.SERVER == server_type,
                MEDIASYNCITEMS.ITEM_ID == iteminfo.get("id")
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
            self.session.add(new_item)
            self.session.commit()
            return True
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            self.session.rollback()
            return False
        finally:
            self._close_session()

    def empty(self, server_type=None, library=None):
        try:
            query = self.session.query(MEDIASYNCITEMS)
            if server_type and library:
                query = query.filter(MEDIASYNCITEMS.SERVER == server_type, MEDIASYNCITEMS.LIBRARY == library)
            elif server_type:
                query = query.filter(MEDIASYNCITEMS.SERVER == server_type)
            query.delete()
            self.session.commit()
            return True
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            self.session.rollback()
            return False
        finally:
            self._close_session()

    def statistics(self, server_type, total_count, movie_count, tv_count):
        if not server_type:
            return False
        try:
            # 删除旧统计
            self.session.query(MEDIASYNCSTATISTIC).filter(
                MEDIASYNCSTATISTIC.SERVER == server_type
            ).delete()
            # 插入新统计
            new_stat = MEDIASYNCSTATISTIC(
                SERVER=server_type,
                TOTAL_COUNT=total_count,
                MOVIE_COUNT=movie_count,
                TV_COUNT=tv_count,
                UPDATE_TIME=time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            )
            self.session.add(new_stat)
            self.session.commit()
            return True
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            self.session.rollback()
            return False
        finally:
            self._close_session()

    @cached(cache=TTLCache(maxsize=128, ttl=60))
    def query(self, server_type, title, year, tmdbid):
        try:
            if not server_type or not title:
                return {}
            
            query = self.session.query(MEDIASYNCITEMS).filter(
                MEDIASYNCITEMS.SERVER == server_type
            )
            
            if tmdbid:
                item = query.filter(MEDIASYNCITEMS.TMDBID == tmdbid).first()
                if item:
                    return item
            
            if year:
                item = query.filter(
                    MEDIASYNCITEMS.TITLE == title,
                    MEDIASYNCITEMS.YEAR == year
                ).first()
            else:
                item = query.filter(MEDIASYNCITEMS.TITLE == title).first()
            
            return item if item else {}
        finally:
            self._close_session()

    def get_statistics(self, server_type):
        try:
            if not server_type:
                return None
            return self.session.query(MEDIASYNCSTATISTIC).filter(
                MEDIASYNCSTATISTIC.SERVER == server_type
            ).first()
        finally:
            self._close_session()

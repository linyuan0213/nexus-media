"""
Plugin Repository
Handles plugin history and TMDB blacklist related database operations.
"""
import time

from app.db import DbPersist
from app.db.models import PLUGINHISTORY, TMDBBLACKLIST
from app.db.repositories.base_repository import BaseRepository


class PluginRepository(BaseRepository):
    """
    插件历史仓储
    处理插件历史和TMDB黑名单的数据库操作
    """

    # ==================== Plugin History ====================

    @DbPersist(BaseRepository._db)
    def insert_plugin_history(self, plugin_id, key, value):
        """
        新增插件运行记录
        
        Args:
            plugin_id: 插件ID
            key: 键
            value: 值
        """
        self._db.insert(PLUGINHISTORY(
            PLUGIN_ID=plugin_id,
            KEY=key,
            VALUE=value,
            DATE=time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))
        ))

    def get_plugin_history(self, plugin_id, key):
        """
        查询插件运行记录
        
        Args:
            plugin_id: 插件ID
            key: 键，None则返回所有记录
            
        Returns:
            历史记录
        """
        if not plugin_id:
            return None
        if key:
            return self._db.query(PLUGINHISTORY).filter(plugin_id == PLUGINHISTORY.PLUGIN_ID,
                                                        key == PLUGINHISTORY.KEY).first()
        else:
            return self._db.query(PLUGINHISTORY).filter(plugin_id == PLUGINHISTORY.PLUGIN_ID).all()

    @DbPersist(BaseRepository._db)
    def update_plugin_history(self, plugin_id, key, value):
        """
        更新插件运行记录
        
        Args:
            plugin_id: 插件ID
            key: 键
            value: 值
        """
        self._db.query(PLUGINHISTORY).filter(plugin_id == PLUGINHISTORY.PLUGIN_ID,
                                              key == PLUGINHISTORY.KEY).update({
            "VALUE": value
        })

    @DbPersist(BaseRepository._db)
    def delete_plugin_history(self, plugin_id, key):
        """
        删除插件运行记录
        
        Args:
            plugin_id: 插件ID
            key: 键
        """
        self._db.query(PLUGINHISTORY).filter(plugin_id == PLUGINHISTORY.PLUGIN_ID,
                                              key == PLUGINHISTORY.KEY).delete()

    # ==================== TMDB Blacklist ====================

    def is_tmdb_blacklisted(self, tmdb_id, media_type=None):
        """
        检查TMDB ID是否在黑名单中
        
        Args:
            tmdb_id: TMDB ID
            media_type: 媒体类型
            
        Returns:
            是否在黑名单中
        """
        if not tmdb_id:
            return False
        if media_type:
            count = self._db.query(TMDBBLACKLIST).filter(
                str(tmdb_id) == TMDBBLACKLIST.TMDB_ID,
                media_type == TMDBBLACKLIST.MEDIA_TYPE
            ).count()
        else:
            count = self._db.query(TMDBBLACKLIST).filter(
                str(tmdb_id) == TMDBBLACKLIST.TMDB_ID
            ).count()
        return count > 0

    def get_tmdb_blacklist(self):
        """
        获取所有TMDB黑名单记录
        
        Returns:
            黑名单记录列表
        """
        return self._db.query(TMDBBLACKLIST).all()

    @DbPersist(BaseRepository._db)
    def insert_tmdb_blacklist(self, tmdb_id, title=None, year=None,
                              media_type=None, poster_path=None, backdrop_path=None, note=None):
        """
        添加到TMDB黑名单
        
        Args:
            tmdb_id: TMDB ID
            title: 标题
            year: 年份
            media_type: 媒体类型
            poster_path: 海报路径
            backdrop_path: 背景图路径
            note: 备注
        """
        if not tmdb_id or self.is_tmdb_blacklisted(tmdb_id, media_type):
            return

        self._db.insert(TMDBBLACKLIST(
            TMDB_ID=str(tmdb_id),
            TITLE=title,
            YEAR=year,
            MEDIA_TYPE=media_type,
            POSTER_PATH=poster_path,
            BACKDROP_PATH=backdrop_path,
            NOTE=note
        ))

    @DbPersist(BaseRepository._db)
    def delete_tmdb_blacklist(self, tmdb_id, media_type=None):
        """
        从TMDB黑名单删除
        
        Args:
            tmdb_id: TMDB ID
            media_type: 媒体类型
        """
        if not tmdb_id:
            return
        if media_type:
            self._db.query(TMDBBLACKLIST).filter(
                str(tmdb_id) == TMDBBLACKLIST.TMDB_ID,
                media_type == TMDBBLACKLIST.MEDIA_TYPE
            ).delete()
        else:
            self._db.query(TMDBBLACKLIST).filter(
                str(tmdb_id) == TMDBBLACKLIST.TMDB_ID
            ).delete()

    @DbPersist(BaseRepository._db)
    def clear_tmdb_blacklist(self):
        """
        清空所有TMDB黑名单记录
        """
        self._db.query(TMDBBLACKLIST).delete()

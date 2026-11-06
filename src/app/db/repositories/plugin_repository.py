"""
Plugin Repository
Handles plugin history and TMDB blacklist related database operations.
"""

import time

from app.db.models import METADATABLACKLIST, PLUGINHISTORY
from app.db.repositories.base_repository import BaseRepository


class PluginRepository(BaseRepository):
    """
    插件历史仓储
    处理插件历史和识别黑名单的数据库操作
    """

    # ==================== Plugin History ====================

    def insert_plugin_history(self, plugin_id, key, value):
        """
        新增插件运行记录

        Args:
            plugin_id: 插件ID
            key: 键
            value: 值
        """
        with self.session() as db:
            db.add(
                PLUGINHISTORY(
                    PLUGIN_ID=plugin_id,
                    KEY=key,
                    VALUE=value,
                    DATE=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time())),
                )
            )

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
        with self.session() as db:
            if key:
                return (
                    db.query(PLUGINHISTORY)
                    .filter(plugin_id == PLUGINHISTORY.PLUGIN_ID, key == PLUGINHISTORY.KEY)
                    .first()
                )
            return db.query(PLUGINHISTORY).filter(plugin_id == PLUGINHISTORY.PLUGIN_ID).all()

    def update_plugin_history(self, plugin_id, key, value):
        """
        更新插件运行记录

        Args:
            plugin_id: 插件ID
            key: 键
            value: 值
        """
        with self.session() as db:
            db.query(PLUGINHISTORY).filter(plugin_id == PLUGINHISTORY.PLUGIN_ID, key == PLUGINHISTORY.KEY).update(
                {"VALUE": value}
            )

    def delete_plugin_history(self, plugin_id, key):
        """
        删除插件运行记录

        Args:
            plugin_id: 插件ID
            key: 键
        """
        with self.session() as db:
            db.query(PLUGINHISTORY).filter(plugin_id == PLUGINHISTORY.PLUGIN_ID, key == PLUGINHISTORY.KEY).delete()

    # ==================== 识别黑名单 ====================

    def is_blacklisted(self, provider, external_id, media_type=None):
        """检查 provider 引用是否在黑名单中."""
        if not external_id:
            return False
        with self.session() as db:
            query = db.query(METADATABLACKLIST).filter(
                METADATABLACKLIST.PROVIDER == str(provider),
                METADATABLACKLIST.EXTERNAL_ID == str(external_id),
            )
            if media_type:
                query = query.filter(METADATABLACKLIST.MEDIA_TYPE == media_type)
            return query.count() > 0

    def get_blacklist(self, provider=None):
        """获取识别黑名单记录."""
        with self.session() as db:
            query = db.query(METADATABLACKLIST)
            if provider:
                query = query.filter(METADATABLACKLIST.PROVIDER == str(provider))
            return query.all()

    def insert_blacklist(
        self,
        provider,
        external_id,
        title=None,
        year=None,
        media_type=None,
        poster_path=None,
        backdrop_path=None,
        note=None,
    ):
        """添加到识别黑名单."""
        if not external_id:
            return
        with self.session() as db:
            query = db.query(METADATABLACKLIST).filter(
                METADATABLACKLIST.PROVIDER == str(provider),
                METADATABLACKLIST.EXTERNAL_ID == str(external_id),
            )
            if media_type:
                query = query.filter(METADATABLACKLIST.MEDIA_TYPE == media_type)
            if query.first():
                return

            db.add(
                METADATABLACKLIST(
                    PROVIDER=str(provider),
                    EXTERNAL_ID=str(external_id),
                    TITLE=title or "",
                    YEAR=year or "",
                    MEDIA_TYPE=media_type or "",
                    POSTER_PATH=poster_path or "",
                    BACKDROP_PATH=backdrop_path or "",
                    NOTE=note or "",
                )
            )

    def delete_blacklist(self, provider, external_id, media_type=None):
        """从识别黑名单删除."""
        if not external_id:
            return
        with self.session() as db:
            query = db.query(METADATABLACKLIST).filter(
                METADATABLACKLIST.PROVIDER == str(provider),
                METADATABLACKLIST.EXTERNAL_ID == str(external_id),
            )
            if media_type:
                query = query.filter(METADATABLACKLIST.MEDIA_TYPE == media_type)
            query.delete()

    def clear_blacklist(self, provider=None):
        """清空识别黑名单记录."""
        with self.session() as db:
            query = db.query(METADATABLACKLIST)
            if provider:
                query = query.filter(METADATABLACKLIST.PROVIDER == str(provider))
            query.delete()

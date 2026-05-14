"""
Sync Repository
Handles directory sync related database operations.
"""

from app.db import DbPersist
from app.db.models import CONFIGSYNCPATHS
from app.db.repositories.base_repository import BaseRepository


class SyncRepository(BaseRepository):
    """
    目录同步仓储
    处理目录同步配置的数据库操作
    """

    @DbPersist(BaseRepository._db)
    def insert_config_sync_path(self, source, dest, unknown, mode, compatibility, rename, enabled, note=None):
        """
        增加目录同步
        
        Args:
            source: 源目录
            dest: 目标目录
            unknown: 未识别目录
            mode: 同步模式
            compatibility: 兼容性模式
            rename: 是否重命名
            enabled: 是否启用
            note: 备注
        """
        return self._db.insert(CONFIGSYNCPATHS(
            SOURCE=source,
            DEST=dest,
            UNKNOWN=unknown,
            MODE=mode,
            COMPATIBILITY=int(compatibility),
            RENAME=int(rename),
            ENABLED=int(enabled),
            NOTE=note
        ))

    @DbPersist(BaseRepository._db)
    def delete_config_sync_path(self, sid):
        """
        删除目录同步
        
        Args:
            sid: 同步配置ID
        """
        if not sid:
            return
        self._db.query(CONFIGSYNCPATHS).filter(int(sid) == CONFIGSYNCPATHS.ID).delete()

    def get_config_sync_paths(self, sid=None):
        """
        查询目录同步
        
        Args:
            sid: 同步配置ID
            
        Returns:
            同步配置列表
        """
        if sid:
            return self._db.query(CONFIGSYNCPATHS).filter(int(sid) == CONFIGSYNCPATHS.ID).all()
        return self._db.query(CONFIGSYNCPATHS).order_by(CONFIGSYNCPATHS.SOURCE).all()

    @DbPersist(BaseRepository._db)
    def check_config_sync_paths(self, sid=None, compatibility=None, rename=None, enabled=None):
        """
        设置目录同步状态
        
        Args:
            sid: 同步配置ID
            compatibility: 兼容性模式
            rename: 是否重命名
            enabled: 是否启用
        """
        if sid and rename is not None:
            self._db.query(CONFIGSYNCPATHS).filter(int(sid) == CONFIGSYNCPATHS.ID).update({
                "RENAME": int(rename)
            })
        elif sid and enabled is not None:
            self._db.query(CONFIGSYNCPATHS).filter(int(sid) == CONFIGSYNCPATHS.ID).update({
                "ENABLED": int(enabled)
            })
        elif sid and compatibility is not None:
            self._db.query(CONFIGSYNCPATHS).filter(int(sid) == CONFIGSYNCPATHS.ID).update({
                "COMPATIBILITY": int(compatibility)
            })

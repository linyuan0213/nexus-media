# -*- coding: utf-8 -*-
"""
同步领域 Repository 适配器
将旧版 SyncRepository 适配为新领域接口
"""
from typing import List, Optional

from app.domain.entities.sync import SyncPathEntity
from app.domain.interfaces.sync_repo import ISyncPathRepository
from app.db.repositories.sync_repository import SyncRepository


class SyncPathRepositoryAdapter(ISyncPathRepository):
    """目录同步路径仓储适配器"""

    def __init__(self, repo: Optional[SyncRepository] = None):
        self._repo = repo or SyncRepository()

    def get_all(self, sid: Optional[int] = None) -> List[SyncPathEntity]:
        rows = self._repo.get_config_sync_paths(sid)
        if not rows:
            return []
        return [entity for entity in [SyncPathEntity.from_orm(r) for r in rows] if entity is not None]

    # 兼容旧Repository方法名
    def get_config_sync_paths(self, sid=None):
        return self._repo.get_config_sync_paths(sid)

    def insert(self, source: str, dest: str, unknown: str, mode: str,
               compatibility: int, rename: int, enabled: int, note: Optional[str] = None) -> None:
        self._repo.insert_config_sync_path(source, dest, unknown, mode, compatibility, rename, enabled, note)

    # 兼容旧Repository方法名
    def insert_config_sync_path(self, source, dest, unknown, mode, compatibility, rename, enabled, note=None):
        self._repo.insert_config_sync_path(source, dest, unknown, mode, compatibility, rename, enabled, note)

    def delete(self, sid: int) -> None:
        self._repo.delete_config_sync_path(sid)

    # 兼容旧Repository方法名
    def delete_config_sync_path(self, sid):
        self._repo.delete_config_sync_path(sid)

    def update_state(self, sid: Optional[int] = None, compatibility: Optional[int] = None,
                     rename: Optional[int] = None, enabled: Optional[int] = None) -> None:
        self._repo.check_config_sync_paths(sid, compatibility, rename, enabled)

    # 兼容旧Repository方法名
    def check_config_sync_paths(self, sid=None, compatibility=None, rename=None, enabled=None):
        self._repo.check_config_sync_paths(sid, compatibility, rename, enabled)

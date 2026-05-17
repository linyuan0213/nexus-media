"""
同步领域 Repository 适配器
将旧版 SyncRepository 适配为新领域接口
"""

from app.db.repositories.sync_repository import SyncRepository
from app.domain.entities.sync import SyncPathEntity
from app.domain.interfaces.sync_repo import ISyncPathRepository


class SyncPathRepositoryAdapter(ISyncPathRepository):
    """目录同步路径仓储适配器"""

    def __init__(self, repo: SyncRepository | None = None):
        self._repo = repo or SyncRepository()

    def get_all(self, sid: int | None = None) -> list[SyncPathEntity]:
        rows = self._repo.get_config_sync_paths(sid)
        if not rows:
            return []
        return [entity for entity in [SyncPathEntity.from_orm(r) for r in rows] if entity is not None]

    # 兼容旧Repository方法名
    def get_config_sync_paths(self, sid=None):
        return self._repo.get_config_sync_paths(sid)

    def insert(
        self,
        source: str,
        dest: str,
        unknown: str,
        mode: str,
        compatibility: int,
        rename: int,
        enabled: int,
        note: str | None = None,
        operation: str | None = None,
        src_backend: str | None = None,
        dst_backend: str | None = None,
    ) -> None:
        self._repo.insert_config_sync_path(
            source, dest, unknown, mode, compatibility, rename, enabled, note, operation, src_backend, dst_backend
        )

    # 兼容旧Repository方法名
    def insert_config_sync_path(
        self, source, dest, unknown, mode, compatibility, rename, enabled, note=None, operation=None, src_backend=None, dst_backend=None
    ):
        self._repo.insert_config_sync_path(
            source, dest, unknown, mode, compatibility, rename, enabled, note, operation, src_backend, dst_backend
        )

    def delete(self, sid: int) -> None:
        self._repo.delete_config_sync_path(sid)

    # 兼容旧Repository方法名
    def delete_config_sync_path(self, sid):
        self._repo.delete_config_sync_path(sid)

    def update_state(
        self,
        sid: int | None = None,
        compatibility: int | None = None,
        rename: int | None = None,
        enabled: int | None = None,
    ) -> None:
        self._repo.check_config_sync_paths(sid, compatibility, rename, enabled)

    # 兼容旧Repository方法名
    def check_config_sync_paths(self, sid=None, compatibility=None, rename=None, enabled=None):
        self._repo.check_config_sync_paths(sid, compatibility, rename, enabled)

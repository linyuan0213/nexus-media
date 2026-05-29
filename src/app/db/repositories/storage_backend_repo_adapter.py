"""
存储后端领域 Repository 适配器
将旧版 StorageBackendRepository 适配为新领域接口
"""

from app.db.repositories.storage_backend_repository import StorageBackendRepository
from app.domain.entities.storage_backend import StorageBackendEntity
from app.domain.interfaces.storage_backend_repo import IStorageBackendRepository


class StorageBackendRepositoryAdapter(IStorageBackendRepository):
    """存储后端仓储适配器"""

    def __init__(self, repo: StorageBackendRepository | None = None):
        self._repo = repo or StorageBackendRepository()

    def get_all(self) -> list[StorageBackendEntity]:
        rows = self._repo.get_all()
        return [e for e in [StorageBackendEntity.from_orm(r) for r in rows] if e is not None]

    def get_by_id(self, sid: int) -> StorageBackendEntity | None:
        row = self._repo.get_by_id(sid)
        return StorageBackendEntity.from_orm(row)

    def insert(self, name: str, type: str, config: str, enabled: int = 1) -> int:
        return self._repo.insert(name, type, config, enabled)

    def update(self, sid: int, **kwargs) -> None:
        self._repo.update(sid, **kwargs)

    def delete(self, sid: int) -> None:
        self._repo.delete(sid)

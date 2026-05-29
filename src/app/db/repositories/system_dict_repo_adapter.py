"""
系统字典领域 Repository 适配器
"""

from app.db.repositories.system_dict_repository import SystemDictRepository
from app.domain.entities.system_dict import SystemDictEntity
from app.domain.interfaces.system_dict_repo import ISystemDictRepository


class SystemDictRepositoryAdapter(ISystemDictRepository):
    """系统字典仓储适配器"""

    def __init__(self, repo: SystemDictRepository | None = None):
        self._repo = repo or SystemDictRepository()

    def get_by_type_key(self, dtype: str, key: str) -> SystemDictEntity | None:
        row = self._repo.get_by_type_key(dtype, key)
        return SystemDictEntity.from_orm(row)

    def list_by_type(self, dtype: str) -> list[SystemDictEntity]:
        rows = self._repo.list_by_type(dtype)
        return [e for e in [SystemDictEntity.from_orm(r) for r in rows] if e is not None]

    def set(self, dtype: str, key: str, value: str, note: str = "") -> bool:
        return self._repo.set(dtype, key, value, note)

    def delete(self, dtype: str, key: str) -> bool:
        return self._repo.delete(dtype, key)

    def exists(self, dtype: str, key: str) -> bool:
        return self._repo.exists(dtype, key)

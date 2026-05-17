"""
存储后端领域 Repository 接口
"""

from typing import Protocol

from app.domain.entities.storage_backend import StorageBackendEntity


class IStorageBackendRepository(Protocol):
    """存储后端仓储接口"""

    def get_all(self) -> list[StorageBackendEntity]:
        """查询所有存储后端配置"""
        ...

    def get_by_id(self, sid: int) -> StorageBackendEntity | None:
        """根据ID查询存储后端配置"""
        ...

    def insert(self, name: str, type: str, config: str, enabled: int = 1) -> int:
        """插入存储后端配置"""
        ...

    def update(self, sid: int, **kwargs) -> None:
        """更新存储后端配置"""
        ...

    def delete(self, sid: int) -> None:
        """删除存储后端配置"""
        ...

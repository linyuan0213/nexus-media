"""Storage backend service - 存储后端配置业务层."""

from app.db.repositories.storage_backend_repo_adapter import StorageBackendRepositoryAdapter
from app.di import container


class StorageBackendService:
    """存储后端配置业务服务"""

    def __init__(self, repo: StorageBackendRepositoryAdapter | None = None):
        self._repo = repo or container.storage_backend_repo()

    def list_backends(self) -> list[dict]:
        """获取所有存储后端列表"""
        items = self._repo.get_all()
        return [e.to_dict() for e in items]

    def get_backend(self, sid: int) -> dict | None:
        """根据 ID 获取存储后端详情"""
        entity = self._repo.get_by_id(sid)
        if not entity:
            return None
        return entity.to_dict()

    def create_backend(self, name: str, type: str, config: str, enabled: int = 1) -> int:
        """创建存储后端，返回新记录 ID"""
        return self._repo.insert(name, type, config, enabled)

    def update_backend(self, sid: int, **kwargs) -> None:
        """更新存储后端"""
        self._repo.update(sid, **kwargs)

    def delete_backend(self, sid: int) -> None:
        """删除存储后端"""
        self._repo.delete(sid)

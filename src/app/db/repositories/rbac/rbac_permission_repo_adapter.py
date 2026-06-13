"""
RBAC 领域 Repository 适配器
将旧版 RBACRepository 适配为新领域接口
"""

from typing import cast

from app.db.repositories.rbac.rbac_permission_repository import RBACPermissionRepository
from app.domain.entities.rbac import (
    RBACPermissionEntity,
)
from app.domain.interfaces.rbac_repo import (
    IRBACPermissionRepository,
)


class RBACPermissionRepositoryAdapter(IRBACPermissionRepository):
    """RBAC权限仓储适配器"""

    def __init__(self, repo: RBACPermissionRepository | None = None):
        self._repo = repo or RBACPermissionRepository()

    def get_permission_by_id(self, permission_id: int) -> RBACPermissionEntity | None:
        row = self._repo.get_permission_by_id(permission_id)
        return RBACPermissionEntity.from_orm(row)

    def get_permission_by_code(self, permission_code: str) -> RBACPermissionEntity | None:
        row = self._repo.get_permission_by_code(permission_code)
        return RBACPermissionEntity.from_orm(row)

    def get_all_permissions(
        self, module: str | None = None, permission_type: str | None = None
    ) -> list[RBACPermissionEntity]:
        rows = self._repo.get_all_permissions(module=module, permission_type=permission_type)
        return [e for e in [RBACPermissionEntity.from_orm(r) for r in rows] if e is not None]

    def get_permissions_by_codes(self, codes: list[str]) -> list[RBACPermissionEntity]:
        rows = self._repo.get_permissions_by_codes(codes)
        return [e for e in [RBACPermissionEntity.from_orm(r) for r in rows] if e is not None]

    def create_permission(
        self,
        permission_name: str,
        permission_code: str,
        permission_type: str = "api",
        module: str | None = None,
        description: str | None = None,
    ) -> RBACPermissionEntity:
        row = self._repo.create_permission(permission_name, permission_code, permission_type, module, description)
        if isinstance(row, bool):
            row = self._repo.get_permission_by_code(permission_code)
        return cast(RBACPermissionEntity, RBACPermissionEntity.from_orm(row))

    def update_permission(self, permission_id: int, **kwargs) -> bool:
        return self._repo.update_permission(permission_id, **kwargs)

    def delete_permission(self, permission_id: int) -> bool:
        return self._repo.delete_permission(permission_id)

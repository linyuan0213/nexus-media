"""
RBAC 领域 Repository 适配器
将旧版 RBACRepository 适配为新领域接口
"""

from typing import cast

from app.db.repositories.rbac.rbac_role_repository import RBACRoleRepository
from app.domain.entities.rbac import (
    RBACMenuEntity,
    RBACPermissionEntity,
    RBACRoleEntity,
)
from app.domain.interfaces.rbac_repo import (
    IRBACRoleRepository,
)


class RBACRoleRepositoryAdapter(IRBACRoleRepository):
    """RBAC角色仓储适配器"""

    def __init__(self, repo: RBACRoleRepository | None = None):
        self._repo = repo or RBACRoleRepository()

    def get_role_by_id(self, role_id: int) -> RBACRoleEntity | None:
        row = self._repo.get_role_by_id(role_id)
        return RBACRoleEntity.from_orm(row)

    def get_role_by_code(self, role_code: str) -> RBACRoleEntity | None:
        row = self._repo.get_role_by_code(role_code)
        return RBACRoleEntity.from_orm(row)

    def get_all_roles(self, status: int | None = None) -> list[RBACRoleEntity]:
        rows = self._repo.get_all_roles(status=status)
        return [e for e in [RBACRoleEntity.from_orm(r) for r in rows] if e is not None]

    def get_roles_page(self, page: int = 1, page_size: int = 20) -> tuple[list[RBACRoleEntity], int]:
        rows, total = self._repo.get_roles_page(page=page, page_size=page_size)
        return [e for e in [RBACRoleEntity.from_orm(r) for r in rows] if e is not None], total

    def is_role_exists(self, role_code: str) -> bool:
        return self._repo.is_role_exists(role_code)

    def is_role_name_exists(self, role_name: str) -> bool:
        return self._repo.is_role_name_exists(role_name)

    def create_role(
        self, role_name: str, role_code: str, description: str | None = None, role_level: int = 100
    ) -> RBACRoleEntity:
        row = self._repo.create_role(role_name, role_code, description, role_level)
        if isinstance(row, bool):
            row = self._repo.get_role_by_code(role_code)
        return cast(RBACRoleEntity, RBACRoleEntity.from_orm(row))

    def update_role(self, role_id: int, **kwargs) -> bool:
        return self._repo.update_role(role_id, **kwargs)

    def delete_role(self, role_id: int) -> bool:
        return self._repo.delete_role(role_id)

    def get_role_permissions(self, role_id: int) -> list[RBACPermissionEntity]:
        rows = self._repo.get_role_permissions(role_id)
        return [e for e in [RBACPermissionEntity.from_orm(r) for r in rows] if e is not None]

    def assign_permissions_to_role(self, role_id: int, permission_ids: list[int]) -> bool:
        return self._repo.assign_permissions_to_role(role_id, permission_ids)

    def get_role_menus(self, role_id: int) -> list[RBACMenuEntity]:
        rows = self._repo.get_role_menus(role_id)
        return [e for e in [RBACMenuEntity.from_orm(r) for r in rows] if e is not None]

    def assign_menus_to_role(self, role_id: int, menu_ids: list[int]) -> bool:
        return self._repo.assign_menus_to_role(role_id, menu_ids)

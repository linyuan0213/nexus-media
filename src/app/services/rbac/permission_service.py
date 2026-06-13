"""RBAC permission service - 权限管理."""

from typing import cast

import log
from app.core.exceptions import ResourceAlreadyExistsError, ResourceNotFoundError
from app.db.models.rbac import RBACPermission


class RBACPermissionService:
    """权限管理服务"""

    def __init__(self, permission_repo):
        self.permission_repo = permission_repo

    def create_permission(
        self,
        permission_name: str,
        permission_code: str,
        permission_type: str = "api",
        module: str | None = None,
        description: str | None = None,
    ) -> RBACPermission:
        """创建权限，成功返回权限对象，失败抛出异常."""
        existing = self.permission_repo.get_permission_by_code(permission_code)
        if existing:
            raise ResourceAlreadyExistsError(f"权限代码已存在: {permission_code}")
        permission = self.permission_repo.create_permission(
            permission_name=permission_name,
            permission_code=permission_code,
            permission_type=permission_type,
            module=module,
            description=description,
        )
        log.info(f"[RBAC]创建权限成功: {permission_name}")
        return permission

    def update_permission(self, permission_id: int, **kwargs) -> None:
        """更新权限，失败抛出异常."""
        permission = self.permission_repo.get_permission_by_id(permission_id)
        if not permission:
            raise ResourceNotFoundError(f"权限不存在: id={permission_id}")
        success = self.permission_repo.update_permission(permission_id, **kwargs)
        if not success:
            raise ResourceNotFoundError("更新失败")

    def delete_permission(self, permission_id: int) -> None:
        """删除权限，失败抛出异常."""
        permission = self.permission_repo.get_permission_by_id(permission_id)
        if not permission:
            raise ResourceNotFoundError(f"权限不存在: id={permission_id}")
        success = self.permission_repo.delete_permission(permission_id)
        if not success:
            raise ResourceNotFoundError("删除失败")
        log.info(f"[RBAC]删除权限: {permission.PERMISSION_NAME}")

    def get_all_permissions(self, module: str | None = None) -> list[RBACPermission]:
        return cast(list[RBACPermission], self.permission_repo.get_all_permissions(module=module))

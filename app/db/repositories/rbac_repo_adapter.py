"""
RBAC 领域 Repository 适配器
将旧版 RBACRepository 适配为新领域接口
"""

from typing import Any

from app.db.repositories.rbac_repository import (
    RBACLogRepository,
    RBACMenuRepository,
    RBACPermissionRepository,
    RBACRoleRepository,
    RBACUserRepository,
)
from app.domain.entities.rbac import (
    RBACMenuEntity,
    RBACOperationLogEntity,
    RBACPermissionEntity,
    RBACRoleEntity,
    RBACUserEntity,
    RBACUserLoginLogEntity,
)
from app.domain.interfaces.rbac_repo import (
    IRBACLogRepository,
    IRBACMenuRepository,
    IRBACPermissionRepository,
    IRBACRoleRepository,
    IRBACUserRepository,
)


class RBACUserRepositoryAdapter(IRBACUserRepository):
    """RBAC用户仓储适配器"""

    def __init__(self, repo: RBACUserRepository | None = None):
        self._repo = repo or RBACUserRepository()

    def get_user_by_id(self, user_id: int) -> RBACUserEntity | None:
        row = self._repo.get_user_by_id(user_id)
        return RBACUserEntity.from_orm(row)

    def get_user_by_username(self, username: str) -> RBACUserEntity | None:
        row = self._repo.get_user_by_username(username)
        return RBACUserEntity.from_orm(row)

    def get_user_by_email(self, email: str) -> RBACUserEntity | None:
        row = self._repo.get_user_by_email(email)
        return RBACUserEntity.from_orm(row)

    def get_users(
        self, page: int = 1, page_size: int = 20, status: int | None = None
    ) -> tuple[list[RBACUserEntity], int]:
        rows, total = self._repo.get_users(page=page, page_size=page_size, status=status)
        return [e for e in [RBACUserEntity.from_orm(r) for r in rows] if e is not None], total

    def get_all_users(self) -> list[RBACUserEntity]:
        rows = self._repo.get_all_users()
        return [e for e in [RBACUserEntity.from_orm(r) for r in rows] if e is not None]

    def is_user_exists(self, username: str) -> bool:
        return self._repo.is_user_exists(username)

    def is_email_exists(self, email: str) -> bool:
        return self._repo.is_email_exists(email)

    def create_user(
        self,
        username: str,
        password_hash: str,
        email: str | None = None,
        nickname: str | None = None,
        is_superadmin: int = 0,
    ) -> RBACUserEntity:
        row = self._repo.create_user(username, password_hash, email, nickname, is_superadmin)
        if isinstance(row, bool):
            row = self._repo.get_user_by_username(username)
        return RBACUserEntity.from_orm(row)

    def update_user(self, user_id: int, **kwargs) -> bool:
        return self._repo.update_user(user_id, **kwargs)

    def update_last_login(self, user_id: int, ip: str | None = None) -> bool:
        return self._repo.update_last_login(user_id, ip)

    def delete_user(self, user_id: int) -> bool:
        return self._repo.delete_user(user_id)

    def hard_delete_user(self, user_id: int) -> bool:
        return self._repo.hard_delete_user(user_id)

    def get_user_roles(self, user_id: int) -> list[RBACRoleEntity]:
        rows = self._repo.get_user_roles(user_id)
        return [e for e in [RBACRoleEntity.from_orm(r) for r in rows] if e is not None]

    def assign_roles_to_user(self, user_id: int, role_ids: list[int]) -> bool:
        return self._repo.assign_roles_to_user(user_id, role_ids)

    def add_role_to_user(self, user_id: int, role_id: int) -> bool:
        return self._repo.add_role_to_user(user_id, role_id)

    def remove_role_from_user(self, user_id: int, role_id: int) -> bool:
        return self._repo.remove_role_from_user(user_id, role_id)


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
        return RBACRoleEntity.from_orm(row)

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
        return RBACPermissionEntity.from_orm(row)

    def update_permission(self, permission_id: int, **kwargs) -> bool:
        return self._repo.update_permission(permission_id, **kwargs)

    def delete_permission(self, permission_id: int) -> bool:
        return self._repo.delete_permission(permission_id)


class RBACMenuRepositoryAdapter(IRBACMenuRepository):
    """RBAC菜单仓储适配器"""

    def __init__(self, repo: RBACMenuRepository | None = None):
        self._repo = repo or RBACMenuRepository()

    def get_menu_by_id(self, menu_id: int) -> RBACMenuEntity | None:
        row = self._repo.get_menu_by_id(menu_id)
        return RBACMenuEntity.from_orm(row)

    def get_menu_by_code(self, menu_code: str, include_hidden: bool = True) -> RBACMenuEntity | None:
        row = self._repo.get_menu_by_code(menu_code, include_hidden=include_hidden)
        return RBACMenuEntity.from_orm(row)

    def get_all_menus(self, status: int | None = None) -> list[RBACMenuEntity]:
        rows = self._repo.get_all_menus(status=status)
        return [e for e in [RBACMenuEntity.from_orm(r) for r in rows] if e is not None]

    def get_top_menus(self, include_hidden: bool = False) -> list[RBACMenuEntity]:
        rows = self._repo.get_top_menus(include_hidden=include_hidden)
        return [e for e in [RBACMenuEntity.from_orm(r) for r in rows] if e is not None]

    def get_children_menus(self, parent_id: int) -> list[RBACMenuEntity]:
        rows = self._repo.get_children_menus(parent_id)
        return [e for e in [RBACMenuEntity.from_orm(r) for r in rows] if e is not None]

    def get_menu_tree(self, include_hidden: bool = False) -> list[dict[str, Any]]:
        return self._repo.get_menu_tree(include_hidden=include_hidden)

    def get_user_menus(self, user_id: int) -> list[RBACMenuEntity]:
        rows = self._repo.get_user_menus(user_id)
        return [e for e in [RBACMenuEntity.from_orm(r) for r in rows] if e is not None]

    def create_menu(
        self,
        menu_name: str,
        menu_code: str,
        parent_id: int | None = None,
        path: str | None = None,
        icon: str | None = None,
        component: str | None = None,
        sort_order: int = 0,
        menu_level: int = 1,
        permission_code: str | None = None,
        **kwargs,
    ) -> RBACMenuEntity:
        row = self._repo.create_menu(
            menu_name, menu_code, parent_id, path, icon, component, sort_order, menu_level, permission_code, **kwargs
        )
        if isinstance(row, bool):
            row = self._repo.get_menu_by_code(menu_code)
        return RBACMenuEntity.from_orm(row)

    def update_menu(self, menu_id: int, **kwargs) -> bool:
        return self._repo.update_menu(menu_id, **kwargs)

    def delete_menu(self, menu_id: int) -> bool:
        return self._repo.delete_menu(menu_id)


class RBACLogRepositoryAdapter(IRBACLogRepository):
    """RBAC日志仓储适配器"""

    def __init__(self, repo: RBACLogRepository | None = None):
        self._repo = repo or RBACLogRepository()

    def add_login_log(
        self,
        user_id: int,
        username: str,
        login_ip: str | None = None,
        login_location: str | None = None,
        user_agent: str | None = None,
        login_type: str = "password",
        login_status: int = 1,
        fail_reason: str | None = None,
    ) -> RBACUserLoginLogEntity:
        row = self._repo.add_login_log(
            user_id, username, login_ip, login_location, user_agent, login_type, login_status, fail_reason
        )
        if isinstance(row, bool):
            row = None
        return RBACUserLoginLogEntity.from_orm(row)

    def get_login_logs(
        self, user_id: int | None = None, page: int = 1, page_size: int = 20
    ) -> tuple[list[RBACUserLoginLogEntity], int]:
        rows, total = self._repo.get_login_logs(user_id=user_id, page=page, page_size=page_size)
        return [e for e in [RBACUserLoginLogEntity.from_orm(r) for r in rows] if e is not None], total

    def add_operation_log(
        self,
        user_id: int | None = None,
        username: str | None = None,
        module: str | None = None,
        operation_type: str = "QUERY",
        description: str | None = None,
        request_method: str | None = None,
        request_url: str | None = None,
        request_params: str | None = None,
        response_data: str | None = None,
        operation_ip: str | None = None,
        execution_time: int | None = None,
        operation_status: int = 1,
        error_msg: str | None = None,
    ) -> RBACOperationLogEntity:
        row = self._repo.add_operation_log(
            user_id,
            username,
            module,
            operation_type,
            description,
            request_method,
            request_url,
            request_params,
            response_data,
            operation_ip,
            execution_time,
            operation_status,
            error_msg,
        )
        if isinstance(row, bool):
            row = None
        return RBACOperationLogEntity.from_orm(row)

    def get_operation_logs(
        self, user_id: int | None = None, module: str | None = None, page: int = 1, page_size: int = 20
    ) -> tuple[list[RBACOperationLogEntity], int]:
        rows, total = self._repo.get_operation_logs(user_id=user_id, module=module, page=page, page_size=page_size)
        return [e for e in [RBACOperationLogEntity.from_orm(r) for r in rows] if e is not None], total

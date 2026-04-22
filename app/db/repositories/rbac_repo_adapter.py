# -*- coding: utf-8 -*-
"""
RBAC 领域 Repository 适配器
将旧版 RBACRepository 适配为新领域接口
"""
from typing import Any, Dict, List, Optional, Tuple

from app.domain.entities.rbac import (
    RBACUserEntity,
    RBACRoleEntity,
    RBACPermissionEntity,
    RBACMenuEntity,
    RBACUserLoginLogEntity,
    RBACOperationLogEntity,
)
from app.domain.interfaces.rbac_repo import (
    IRBACUserRepository,
    IRBACRoleRepository,
    IRBACPermissionRepository,
    IRBACMenuRepository,
    IRBACLogRepository,
)
from app.db.repositories.rbac_repository import (
    RBACUserRepository,
    RBACRoleRepository,
    RBACPermissionRepository,
    RBACMenuRepository,
    RBACLogRepository,
)


class RBACUserRepositoryAdapter(IRBACUserRepository):
    """RBAC用户仓储适配器"""

    def __init__(self, repo: Optional[RBACUserRepository] = None):
        self._repo = repo or RBACUserRepository()

    def get_user_by_id(self, user_id: int) -> Optional[RBACUserEntity]:
        row = self._repo.get_user_by_id(user_id)
        return RBACUserEntity.from_orm(row)

    def get_user_by_username(self, username: str) -> Optional[RBACUserEntity]:
        row = self._repo.get_user_by_username(username)
        return RBACUserEntity.from_orm(row)

    def get_user_by_email(self, email: str) -> Optional[RBACUserEntity]:
        row = self._repo.get_user_by_email(email)
        return RBACUserEntity.from_orm(row)

    def get_users(self, page: int = 1, page_size: int = 20, status: Optional[int] = None) -> Tuple[List[RBACUserEntity], int]:
        rows, total = self._repo.get_users(page=page, page_size=page_size, status=status)
        return [e for e in [RBACUserEntity.from_orm(r) for r in rows] if e is not None], total

    def get_all_users(self) -> List[RBACUserEntity]:
        rows = self._repo.get_all_users()
        return [e for e in [RBACUserEntity.from_orm(r) for r in rows] if e is not None]

    def is_user_exists(self, username: str) -> bool:
        return self._repo.is_user_exists(username)

    def is_email_exists(self, email: str) -> bool:
        return self._repo.is_email_exists(email)

    def create_user(self, username: str, password_hash: str, email: Optional[str] = None, nickname: Optional[str] = None, is_superadmin: int = 0) -> RBACUserEntity:
        row = self._repo.create_user(username, password_hash, email, nickname, is_superadmin)
        return RBACUserEntity.from_orm(row)

    def update_user(self, user_id: int, **kwargs) -> bool:
        return self._repo.update_user(user_id, **kwargs)

    def update_last_login(self, user_id: int, ip: Optional[str] = None) -> bool:
        return self._repo.update_last_login(user_id, ip)

    def delete_user(self, user_id: int) -> bool:
        return self._repo.delete_user(user_id)

    def hard_delete_user(self, user_id: int) -> bool:
        return self._repo.hard_delete_user(user_id)

    def get_user_roles(self, user_id: int) -> List[RBACRoleEntity]:
        rows = self._repo.get_user_roles(user_id)
        return [e for e in [RBACRoleEntity.from_orm(r) for r in rows] if e is not None]

    def assign_roles_to_user(self, user_id: int, role_ids: List[int]) -> bool:
        return self._repo.assign_roles_to_user(user_id, role_ids)

    def add_role_to_user(self, user_id: int, role_id: int) -> bool:
        return self._repo.add_role_to_user(user_id, role_id)

    def remove_role_from_user(self, user_id: int, role_id: int) -> bool:
        return self._repo.remove_role_from_user(user_id, role_id)


class RBACRoleRepositoryAdapter(IRBACRoleRepository):
    """RBAC角色仓储适配器"""

    def __init__(self, repo: Optional[RBACRoleRepository] = None):
        self._repo = repo or RBACRoleRepository()

    def get_role_by_id(self, role_id: int) -> Optional[RBACRoleEntity]:
        row = self._repo.get_role_by_id(role_id)
        return RBACRoleEntity.from_orm(row)

    def get_role_by_code(self, role_code: str) -> Optional[RBACRoleEntity]:
        row = self._repo.get_role_by_code(role_code)
        return RBACRoleEntity.from_orm(row)

    def get_all_roles(self, status: Optional[int] = None) -> List[RBACRoleEntity]:
        rows = self._repo.get_all_roles(status=status)
        return [e for e in [RBACRoleEntity.from_orm(r) for r in rows] if e is not None]

    def get_roles_page(self, page: int = 1, page_size: int = 20) -> Tuple[List[RBACRoleEntity], int]:
        rows, total = self._repo.get_roles_page(page=page, page_size=page_size)
        return [e for e in [RBACRoleEntity.from_orm(r) for r in rows] if e is not None], total

    def is_role_exists(self, role_code: str) -> bool:
        return self._repo.is_role_exists(role_code)

    def create_role(self, role_name: str, role_code: str, description: Optional[str] = None, role_level: int = 100) -> RBACRoleEntity:
        row = self._repo.create_role(role_name, role_code, description, role_level)
        return RBACRoleEntity.from_orm(row)

    def update_role(self, role_id: int, **kwargs) -> bool:
        return self._repo.update_role(role_id, **kwargs)

    def delete_role(self, role_id: int) -> bool:
        return self._repo.delete_role(role_id)

    def get_role_permissions(self, role_id: int) -> List[RBACPermissionEntity]:
        rows = self._repo.get_role_permissions(role_id)
        return [e for e in [RBACPermissionEntity.from_orm(r) for r in rows] if e is not None]

    def assign_permissions_to_role(self, role_id: int, permission_ids: List[int]) -> bool:
        return self._repo.assign_permissions_to_role(role_id, permission_ids)

    def get_role_menus(self, role_id: int) -> List[RBACMenuEntity]:
        rows = self._repo.get_role_menus(role_id)
        return [e for e in [RBACMenuEntity.from_orm(r) for r in rows] if e is not None]

    def assign_menus_to_role(self, role_id: int, menu_ids: List[int]) -> bool:
        return self._repo.assign_menus_to_role(role_id, menu_ids)


class RBACPermissionRepositoryAdapter(IRBACPermissionRepository):
    """RBAC权限仓储适配器"""

    def __init__(self, repo: Optional[RBACPermissionRepository] = None):
        self._repo = repo or RBACPermissionRepository()

    def get_permission_by_id(self, permission_id: int) -> Optional[RBACPermissionEntity]:
        row = self._repo.get_permission_by_id(permission_id)
        return RBACPermissionEntity.from_orm(row)

    def get_permission_by_code(self, permission_code: str) -> Optional[RBACPermissionEntity]:
        row = self._repo.get_permission_by_code(permission_code)
        return RBACPermissionEntity.from_orm(row)

    def get_all_permissions(self, module: Optional[str] = None, permission_type: Optional[str] = None) -> List[RBACPermissionEntity]:
        rows = self._repo.get_all_permissions(module=module, permission_type=permission_type)
        return [e for e in [RBACPermissionEntity.from_orm(r) for r in rows] if e is not None]

    def get_permissions_by_codes(self, codes: List[str]) -> List[RBACPermissionEntity]:
        rows = self._repo.get_permissions_by_codes(codes)
        return [e for e in [RBACPermissionEntity.from_orm(r) for r in rows] if e is not None]

    def create_permission(self, permission_name: str, permission_code: str, permission_type: str = 'api', module: Optional[str] = None, description: Optional[str] = None) -> RBACPermissionEntity:
        row = self._repo.create_permission(permission_name, permission_code, permission_type, module, description)
        return RBACPermissionEntity.from_orm(row)

    def update_permission(self, permission_id: int, **kwargs) -> bool:
        return self._repo.update_permission(permission_id, **kwargs)

    def delete_permission(self, permission_id: int) -> bool:
        return self._repo.delete_permission(permission_id)


class RBACMenuRepositoryAdapter(IRBACMenuRepository):
    """RBAC菜单仓储适配器"""

    def __init__(self, repo: Optional[RBACMenuRepository] = None):
        self._repo = repo or RBACMenuRepository()

    def get_menu_by_id(self, menu_id: int) -> Optional[RBACMenuEntity]:
        row = self._repo.get_menu_by_id(menu_id)
        return RBACMenuEntity.from_orm(row)

    def get_menu_by_code(self, menu_code: str, include_hidden: bool = True) -> Optional[RBACMenuEntity]:
        row = self._repo.get_menu_by_code(menu_code, include_hidden=include_hidden)
        return RBACMenuEntity.from_orm(row)

    def get_all_menus(self, status: Optional[int] = None) -> List[RBACMenuEntity]:
        rows = self._repo.get_all_menus(status=status)
        return [e for e in [RBACMenuEntity.from_orm(r) for r in rows] if e is not None]

    def get_top_menus(self, include_hidden: bool = False) -> List[RBACMenuEntity]:
        rows = self._repo.get_top_menus(include_hidden=include_hidden)
        return [e for e in [RBACMenuEntity.from_orm(r) for r in rows] if e is not None]

    def get_children_menus(self, parent_id: int) -> List[RBACMenuEntity]:
        rows = self._repo.get_children_menus(parent_id)
        return [e for e in [RBACMenuEntity.from_orm(r) for r in rows] if e is not None]

    def get_menu_tree(self, include_hidden: bool = False) -> List[Dict[str, Any]]:
        return self._repo.get_menu_tree(include_hidden=include_hidden)

    def get_user_menus(self, user_id: int) -> List[RBACMenuEntity]:
        rows = self._repo.get_user_menus(user_id)
        return [e for e in [RBACMenuEntity.from_orm(r) for r in rows] if e is not None]

    def create_menu(self, menu_name: str, menu_code: str, parent_id: Optional[int] = None, path: Optional[str] = None, icon: Optional[str] = None, component: Optional[str] = None, sort_order: int = 0, menu_level: int = 1, permission_code: Optional[str] = None) -> RBACMenuEntity:
        row = self._repo.create_menu(menu_name, menu_code, parent_id, path, icon, component, sort_order, menu_level, permission_code)
        return RBACMenuEntity.from_orm(row)

    def update_menu(self, menu_id: int, **kwargs) -> bool:
        return self._repo.update_menu(menu_id, **kwargs)

    def delete_menu(self, menu_id: int) -> bool:
        return self._repo.delete_menu(menu_id)


class RBACLogRepositoryAdapter(IRBACLogRepository):
    """RBAC日志仓储适配器"""

    def __init__(self, repo: Optional[RBACLogRepository] = None):
        self._repo = repo or RBACLogRepository()

    def add_login_log(self, user_id: int, username: str, login_ip: Optional[str] = None, login_location: Optional[str] = None, user_agent: Optional[str] = None, login_type: str = 'password', login_status: int = 1, fail_reason: Optional[str] = None) -> RBACUserLoginLogEntity:
        row = self._repo.add_login_log(user_id, username, login_ip, login_location, user_agent, login_type, login_status, fail_reason)
        return RBACUserLoginLogEntity.from_orm(row)

    def get_login_logs(self, user_id: Optional[int] = None, page: int = 1, page_size: int = 20) -> Tuple[List[RBACUserLoginLogEntity], int]:
        rows, total = self._repo.get_login_logs(user_id=user_id, page=page, page_size=page_size)
        return [e for e in [RBACUserLoginLogEntity.from_orm(r) for r in rows] if e is not None], total

    def add_operation_log(self, user_id: Optional[int] = None, username: Optional[str] = None, module: Optional[str] = None, operation_type: str = 'QUERY', description: Optional[str] = None, request_method: Optional[str] = None, request_url: Optional[str] = None, request_params: Optional[str] = None, response_data: Optional[str] = None, operation_ip: Optional[str] = None, execution_time: Optional[int] = None, operation_status: int = 1, error_msg: Optional[str] = None) -> RBACOperationLogEntity:
        row = self._repo.add_operation_log(user_id, username, module, operation_type, description, request_method, request_url, request_params, response_data, operation_ip, execution_time, operation_status, error_msg)
        return RBACOperationLogEntity.from_orm(row)

    def get_operation_logs(self, user_id: Optional[int] = None, module: Optional[str] = None, page: int = 1, page_size: int = 20) -> Tuple[List[RBACOperationLogEntity], int]:
        rows, total = self._repo.get_operation_logs(user_id=user_id, module=module, page=page, page_size=page_size)
        return [e for e in [RBACOperationLogEntity.from_orm(r) for r in rows] if e is not None], total

"""RBAC 角色初始化."""

import log

from app.services.rbac.init.constants import DEFAULT_ROLES
from app.db.repositories.rbac_repo_adapter import RBACPermissionRepositoryAdapter
from app.db.repositories.rbac_repo_adapter import RBACMenuRepositoryAdapter
from app.db.repositories.rbac_repo_adapter import RBACRoleRepositoryAdapter


def init_rbac_roles(
    role_repo=None,
    permission_repo=None,
    menu_repo=None,
):
    """初始化角色数据"""
    role_repo = role_repo or RBACRoleRepositoryAdapter()
    permission_repo = permission_repo or RBACPermissionRepositoryAdapter()
    menu_repo = menu_repo or RBACMenuRepositoryAdapter()
    created_count = 0

    for role_data in DEFAULT_ROLES:
        existing = role_repo.get_role_by_code(role_data["code"])
        if not existing:
            role = role_repo.create_role(
                role_name=role_data["name"],
                role_code=role_data["code"],
                description=role_data["description"],
                role_level=role_data["level"],
            )
            created_count += 1
            log.info(f"[RBAC初始化]创建角色: {role_data['name']}")

            if role_data["permissions"]:
                permissions = permission_repo.get_permissions_by_codes(role_data["permissions"])
                permission_ids = [p.ID for p in permissions]
                if permission_ids:
                    role_repo.assign_permissions_to_role(role.ID, permission_ids)
                    log.info(f"[RBAC初始化]为角色 {role_data['name']} 分配 {len(permission_ids)} 个权限")

            if role_data["menus"]:
                menu_ids = []
                for menu_code in role_data["menus"]:
                    menu = menu_repo.get_menu_by_code(menu_code)
                    if menu:
                        menu_ids.append(menu.ID)
                if menu_ids:
                    role_repo.assign_menus_to_role(role.ID, menu_ids)
                    log.info(f"[RBAC初始化]为角色 {role_data['name']} 分配 {len(menu_ids)} 个菜单")

    log.info(f"[RBAC初始化]角色初始化完成，新增 {created_count} 个角色")
    return created_count

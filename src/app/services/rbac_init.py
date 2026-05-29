"""RBAC初始化模块 — 兼容层，已迁移到 app.services.rbac.init."""

from app.services.rbac.init.menu_init import init_rbac_menus
from app.services.rbac.init.permission_init import init_rbac_permissions
from app.services.rbac.init.role_init import init_rbac_roles
from app.services.rbac.init.system_init import init_admin_user, init_rbac_system

__all__ = [
    "init_admin_user",
    "init_rbac_menus",
    "init_rbac_permissions",
    "init_rbac_roles",
    "init_rbac_system",
]

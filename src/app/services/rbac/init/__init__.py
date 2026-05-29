"""RBAC 初始化包."""

from app.services.rbac.init.system_init import init_admin_user, init_rbac_system

__all__ = ["init_rbac_system", "init_admin_user"]

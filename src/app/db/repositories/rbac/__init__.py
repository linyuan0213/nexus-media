"""RBAC Repository 兼容入口

原 rbac_repository.py 已拆分为 rbac/ 子包，此处保留对旧导入路径的兼容。
"""

from app.db.repositories.rbac.rbac_log_repo_adapter import RBACLogRepositoryAdapter
from app.db.repositories.rbac.rbac_log_repository import RBACLogRepository
from app.db.repositories.rbac.rbac_menu_repo_adapter import RBACMenuRepositoryAdapter
from app.db.repositories.rbac.rbac_menu_repository import RBACMenuRepository
from app.db.repositories.rbac.rbac_permission_repo_adapter import RBACPermissionRepositoryAdapter
from app.db.repositories.rbac.rbac_permission_repository import RBACPermissionRepository
from app.db.repositories.rbac.rbac_role_repo_adapter import RBACRoleRepositoryAdapter
from app.db.repositories.rbac.rbac_role_repository import RBACRoleRepository
from app.db.repositories.rbac.rbac_user_repo_adapter import RBACUserRepositoryAdapter
from app.db.repositories.rbac.rbac_user_repository import RBACUserRepository

__all__ = [
    "RBACUserRepository",
    "RBACRoleRepository",
    "RBACPermissionRepository",
    "RBACMenuRepository",
    "RBACLogRepository",
    "RBACUserRepositoryAdapter",
    "RBACRoleRepositoryAdapter",
    "RBACPermissionRepositoryAdapter",
    "RBACMenuRepositoryAdapter",
    "RBACLogRepositoryAdapter",
]

"""RBAC Service Layer — 兼容层，已迁移到 app.services.rbac 子包."""

from app.services.rbac.check_service import require_any_permission, require_permission
from app.services.rbac.service import RBACService

__all__ = [
    "RBACService",
    "require_any_permission",
    "require_permission",
]

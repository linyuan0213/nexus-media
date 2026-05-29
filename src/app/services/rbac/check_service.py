"""RBAC check service - 权限检查."""

from functools import wraps


class RBACCheckService:
    """权限检查服务"""

    def __init__(self, user_repo, role_repo, permission_repo, menu_repo):
        self.user_repo = user_repo
        self.role_repo = role_repo
        self.permission_repo = permission_repo
        self.menu_repo = menu_repo

    def get_user_permissions(self, user_id: int) -> set[str]:
        """获取用户的所有权限代码"""
        user = self.user_repo.get_user_by_id(user_id)
        if not user:
            return set()
        if user.is_superadmin == 1:
            all_permissions = self.permission_repo.get_all_permissions()
            return {p.permission_code for p in all_permissions}
        permissions = set()
        roles = self.user_repo.get_user_roles(user_id)
        for role in roles:
            if role.status == 1:
                role_permissions = self.role_repo.get_role_permissions(role.id)
                for perm in role_permissions:
                    if perm.status == 1:
                        permissions.add(perm.permission_code)
        return permissions

    def check_permission(self, user_id: int, permission_code: str) -> bool:
        """检查用户是否拥有指定权限"""
        user = self.user_repo.get_user_by_id(user_id)
        if not user:
            return False
        if user.IS_SUPERADMIN == 1:
            return True
        permissions = self.get_user_permissions(user_id)
        return permission_code in permissions

    def check_any_permission(self, user_id: int, permission_codes: list[str]) -> bool:
        """检查用户是否拥有任一指定权限"""
        user = self.user_repo.get_user_by_id(user_id)
        if not user:
            return False
        if user.IS_SUPERADMIN == 1:
            return True
        permissions = self.get_user_permissions(user_id)
        return any(code in permissions for code in permission_codes)

    def check_all_permissions(self, user_id: int, permission_codes: list[str]) -> bool:
        """检查用户是否拥有所有指定权限"""
        user = self.user_repo.get_user_by_id(user_id)
        if not user:
            return False
        if user.IS_SUPERADMIN == 1:
            return True
        permissions = self.get_user_permissions(user_id)
        return all(code in permissions for code in permission_codes)

    def check_menu_access(self, user_id: int, menu_code: str) -> bool:
        """检查用户是否有权访问指定菜单"""
        user = self.user_repo.get_user_by_id(user_id)
        if not user:
            return False
        if user.IS_SUPERADMIN == 1:
            return True
        user_menus = self.menu_repo.get_user_menus(user_id)
        menu_codes = {m.MENU_CODE for m in user_menus}
        return menu_code in menu_codes


def require_permission(permission_code: str):
    """权限检查装饰器（向后兼容，内部逻辑已迁移到 FastAPI deps）"""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        return wrapper

    return decorator


def require_any_permission(permission_codes: list[str]):
    """任一权限检查装饰器（向后兼容，内部逻辑已迁移到 FastAPI deps）"""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        return wrapper

    return decorator

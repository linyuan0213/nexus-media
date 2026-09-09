"""RBAC check service - 权限检查."""

from dataclasses import dataclass
from functools import wraps

from app.infrastructure.cache_system import RBACSnapshotCache


@dataclass(frozen=True)
class UserAuthSnapshot:
    """用户权限快照：权限码 + 角色码（服务端缓存，授权变更即时失效）"""

    permissions: frozenset[str]
    role_codes: frozenset[str]


class RBACCheckService:
    """权限检查服务"""

    _SNAPSHOT_KEY = "rbac_snapshot:{user_id}"

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
        permissions = set()
        roles = self.user_repo.get_user_roles(user_id)
        for role in roles:
            if role.status == 1:
                role_permissions = self.role_repo.get_role_permissions(role.id)
                for perm in role_permissions:
                    if perm.status == 1:
                        permissions.add(perm.permission_code)
        return permissions

    def get_user_role_codes(self, user_id: int) -> set[str]:
        """获取用户启用角色的角色码列表"""
        if not self.user_repo.get_user_by_id(user_id):
            return set()
        codes = set()
        for role in self.user_repo.get_user_roles(user_id):
            if role.status == 1:
                code = getattr(role, "role_code", None) or getattr(role, "ROLE_CODE", None)
                if code:
                    codes.add(str(code))
        return codes

    def get_user_snapshot(self, user_id: int) -> UserAuthSnapshot:
        """获取用户权限快照（带缓存，授权变更应调用 invalidate_* 主动失效）"""
        key = self._SNAPSHOT_KEY.format(user_id=user_id)
        cached = RBACSnapshotCache.get(key)
        if cached is not None:
            return cached
        snapshot = UserAuthSnapshot(
            permissions=frozenset(self.get_user_permissions(user_id)),
            role_codes=frozenset(self.get_user_role_codes(user_id)),
        )
        RBACSnapshotCache.set(key, snapshot)
        return snapshot

    def invalidate_user(self, user_id: int) -> None:
        """使用户权限快照失效（用户角色变更、用户删除时调用）"""
        RBACSnapshotCache.delete(self._SNAPSHOT_KEY.format(user_id=user_id))

    def invalidate_all(self) -> None:
        """全量失效（角色权限变更、角色删除时调用）"""
        RBACSnapshotCache.clear()

    def check_permission(self, user_id: int, permission_code: str) -> bool:
        """检查用户是否拥有指定权限"""
        if not self.user_repo.get_user_by_id(user_id):
            return False
        return permission_code in self.get_user_snapshot(user_id).permissions

    def check_any_permission(self, user_id: int, permission_codes: list[str]) -> bool:
        """检查用户是否拥有任一指定权限"""
        if not self.user_repo.get_user_by_id(user_id):
            return False
        permissions = self.get_user_snapshot(user_id).permissions
        return any(code in permissions for code in permission_codes)

    def check_all_permissions(self, user_id: int, permission_codes: list[str]) -> bool:
        """检查用户是否拥有所有指定权限"""
        if not self.user_repo.get_user_by_id(user_id):
            return False
        permissions = self.get_user_snapshot(user_id).permissions
        return all(code in permissions for code in permission_codes)

    def check_menu_access(self, user_id: int, menu_code: str) -> bool:
        """检查用户是否有权访问指定菜单"""
        if not self.user_repo.get_user_by_id(user_id):
            return False
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

"""RBAC 权限快照缓存测试."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.infrastructure.cache_system import RBACSnapshotCache
from app.services.rbac.check_service import RBACCheckService, UserAuthSnapshot


def _make_service(user_exists: bool = True, roles: list | None = None, permissions: list[str] | None = None):
    user_repo = MagicMock()
    role_repo = MagicMock()
    permission_repo = MagicMock()
    menu_repo = MagicMock()

    user_repo.get_user_by_id.return_value = SimpleNamespace(id=1) if user_exists else None
    user_repo.get_user_roles.return_value = roles or []
    role_repo.get_role_permissions.return_value = [
        SimpleNamespace(status=1, permission_code=p) for p in (permissions or [])
    ]
    return RBACCheckService(user_repo, role_repo, permission_repo, menu_repo), user_repo, role_repo


class TestGetUserSnapshot:
    def setup_method(self):
        RBACSnapshotCache.clear()

    def test_snapshot_contains_permissions_and_role_codes(self):
        roles = [SimpleNamespace(status=1, role_code="user", id=1)]
        svc, _, _ = _make_service(roles=roles, permissions=["download:create"])
        snapshot = svc.get_user_snapshot(1)
        assert snapshot.permissions == frozenset({"download:create"})
        assert snapshot.role_codes == frozenset({"user"})

    def test_snapshot_cached(self):
        roles = [SimpleNamespace(status=1, role_code="user", id=1)]
        svc, user_repo, role_repo = _make_service(roles=roles, permissions=["a"])
        svc.get_user_snapshot(1)
        svc.get_user_snapshot(1)
        # 第二次命中缓存，不再查库（每次未命中快照查询 2 次角色：权限 + 角色码）
        assert user_repo.get_user_roles.call_count == 2
        assert role_repo.get_role_permissions.call_count == 1

    def test_invalidate_user(self):
        roles = [SimpleNamespace(status=1, role_code="user", id=1)]
        svc, user_repo, _ = _make_service(roles=roles, permissions=["a"])
        svc.get_user_snapshot(1)
        svc.invalidate_user(1)
        svc.get_user_snapshot(1)
        assert user_repo.get_user_roles.call_count == 4

    def test_invalidate_all(self):
        roles = [SimpleNamespace(status=1, role_code="user", id=1)]
        svc, user_repo, _ = _make_service(roles=roles, permissions=["a"])
        svc.get_user_snapshot(1)
        svc.invalidate_all()
        svc.get_user_snapshot(1)
        assert user_repo.get_user_roles.call_count == 4

    def test_missing_user_returns_empty_snapshot(self):
        svc, _, _ = _make_service(user_exists=False)
        snapshot = svc.get_user_snapshot(999)
        assert snapshot == UserAuthSnapshot(permissions=frozenset(), role_codes=frozenset())

    def test_disabled_role_excluded(self):
        roles = [
            SimpleNamespace(status=0, role_code="banned", id=1),
            SimpleNamespace(status=1, role_code="user", id=2),
        ]
        svc, _, _ = _make_service(roles=roles, permissions=["x"])
        snapshot = svc.get_user_snapshot(1)
        assert "banned" not in snapshot.role_codes
        assert "user" in snapshot.role_codes

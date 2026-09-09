"""渠道身份绑定服务测试（ADR-021 5.8）."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.infrastructure.cache_system import TokenCache
from app.schemas.auth import SUPERADMIN_ROLE_CODE
from app.services.channel_binding_service import ChannelBindingService


def _make_service(binding=None, user_status=1):
    repo = MagicMock()
    repo.get_binding.return_value = binding
    rbac_service = MagicMock()
    rbac_service.get_user_by_id.return_value = SimpleNamespace(
        ID=7, USERNAME="alice", NICKNAME="Alice", STATUS=user_status, LEVEL=0
    )
    rbac_service.get_user_snapshot.return_value = SimpleNamespace(
        permissions=frozenset({"subscription:manage"}),
        role_codes=frozenset({SUPERADMIN_ROLE_CODE}),
    )
    return ChannelBindingService(repo=repo, rbac_service=rbac_service), repo


class TestBindCodeFlow:
    def setup_method(self):
        TokenCache.delete("channel_bind:000000")

    def test_bind_success(self):
        svc, repo = _make_service()
        from app.infrastructure.cache_system import TokenCache as tc

        tc.set("channel_bind:123456", {"user_id": 7, "attempts": 0}, ttl=600)
        ok, msg = svc.bind_by_code("123456", "telegram", "10001")
        assert ok
        assert "alice" in msg
        repo.bind.assert_called_once_with(7, "telegram", "10001")
        assert tc.get("channel_bind:123456") is None  # 一次性

    def test_invalid_code(self):
        svc, _ = _make_service()
        ok, msg = svc.bind_by_code("999999", "telegram", "10001")
        assert not ok
        assert "无效" in msg or "过期" in msg

    def test_brute_force_lockout(self):
        svc, repo = _make_service()
        from app.infrastructure.cache_system import TokenCache as tc

        tc.set("channel_bind:654321", {"user_id": 999, "attempts": 0}, ttl=600)
        repo.get_binding.return_value = None
        svc._rbac_service.get_user_by_id.return_value = None  # 用户不存在，视为失败尝试
        for _ in range(4):
            ok, _ = svc.bind_by_code("654321", "telegram", "10001")
            assert not ok
        ok, msg = svc.bind_by_code("654321", "telegram", "10001")
        assert not ok
        assert tc.get("channel_bind:654321") is None  # 超限后销毁

    def test_rebind_to_other_user_rejected(self):
        existing = SimpleNamespace(USER_ID=8)
        svc, repo = _make_service(binding=existing)
        ok, msg = svc.bind_direct(7, "telegram", "10001")
        assert not ok
        assert "其他用户" in msg


class TestResolveUser:
    def test_bound_user_resolved_with_snapshot(self):
        binding = SimpleNamespace(USER_ID=7)
        svc, _ = _make_service(binding=binding)
        ctx = svc.resolve_user("telegram", "10001")
        assert ctx is not None
        assert ctx.user_id == 7
        assert ctx.is_superadmin
        assert "subscription:manage" in ctx.permissions

    def test_unbound_returns_none(self):
        svc, _ = _make_service(binding=None)
        assert svc.resolve_user("telegram", "99999") is None

    def test_disabled_user_rejected(self):
        binding = SimpleNamespace(USER_ID=7)
        svc, _ = _make_service(binding=binding, user_status=0)
        assert svc.resolve_user("telegram", "10001") is None

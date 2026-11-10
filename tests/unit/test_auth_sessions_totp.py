"""服务端会话吊销与 TOTP 测试."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pyotp
import pytest

from app.db import init_db
from app.schemas.auth import UserContext
from app.services.auth_service import AuthService
from app.utils.user_agent import describe_user_agent


class _FakeRbac:
    def __init__(self, user=None):
        self.user = user or SimpleNamespace(USERNAME="demo", NICKNAME=None, LEVEL=1)
        self.updated: dict = {}

    def get_user_by_id(self, _user_id):
        return self.user

    def get_user_permissions(self, _user_id):
        return {"media:read"}

    def get_user_role_codes(self, _user_id):
        return {"user"}

    def update_user(self, _user_id, **kwargs):
        self.updated.update(kwargs)


@pytest.fixture(scope="module", autouse=True)
def _schema():
    init_db()


def _ctx(user_id: int = 7):
    return UserContext(user_id=user_id, username="demo", level=1, permissions=[], role_codes=[])


def test_session_is_created_and_can_be_revoked():
    svc = AuthService(rbac_service=MagicMock())
    tokens = svc.create_session_pair(
        _ctx(),
        login_ip="192.0.2.10",
        user_agent=(
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
        ),
    )

    ctx, reason = svc.verify_token_with_session(tokens.access_token)
    assert reason == "ok" and ctx is not None and ctx.session_id
    session_id = ctx.session_id

    sessions = svc.list_sessions(7)
    assert sessions[0]["device_model"] == "iPhone"
    assert sessions[0]["login_ip"] == "192.0.2.10"

    assert svc.revoke_session(session_id, 7) is True
    assert svc.verify_token_with_session(tokens.access_token) == (None, "revoked")


def test_refresh_rotates_refresh_jti_and_rejects_old_token():
    svc = AuthService(rbac_service=_FakeRbac())
    tokens = svc.create_session_pair(_ctx(8), login_ip="127.0.0.1", user_agent="curl/8.0")
    first_ctx = svc.verify_token_with_session(tokens.access_token)[0]
    assert first_ctx is not None and first_ctx.session_id
    session_id = first_ctx.session_id

    refreshed = svc.refresh_access_token(tokens.refresh_token, login_ip="127.0.0.1")
    assert refreshed is not None
    assert svc.refresh_access_token(tokens.refresh_token) is None
    refreshed_ctx = svc.verify_token_with_session(refreshed.access_token)[0]
    assert refreshed_ctx is not None and refreshed_ctx.session_id == session_id


def test_revoke_other_sessions_keeps_current():
    svc = AuthService(rbac_service=MagicMock())
    first = svc.create_session_pair(_ctx(9), login_ip="127.0.0.1", user_agent="curl/1")
    second = svc.create_session_pair(_ctx(9), login_ip="127.0.0.1", user_agent="curl/2")
    current = svc.verify_token_with_session(first.access_token)[0]
    assert current is not None and current.session_id

    assert svc.revoke_other_sessions(9, current.session_id) == 1
    assert svc.verify_token_with_session(second.access_token) == (None, "revoked")
    assert svc.verify_token_with_session(first.access_token)[0] is not None


def test_totp_setup_enable_and_disable():
    user = SimpleNamespace(
        USERNAME="demo", PASSWORD_HASH=AuthService.hash_password("pw"), TOTP_ENABLED=0, TOTP_SECRET=""
    )
    rbac = _FakeRbac(user)
    svc = AuthService(rbac_service=rbac)

    ok, data = svc.begin_totp_setup(7)
    assert ok and data["secret"]
    user.TOTP_SECRET = data["secret"]
    ok, enabled = svc.enable_totp(7, pyotp.TOTP(data["secret"]).now())
    assert ok and len(enabled["recovery_codes"]) == 8
    user.TOTP_ENABLED = 1

    assert svc.totp_status(7)["enabled"] is True
    ok, _ = svc.disable_totp(7, "pw", pyotp.TOTP(data["secret"]).now())
    assert ok


def test_user_agent_device_parser():
    device = describe_user_agent(
        "Mozilla/5.0 (Linux; Android 15; Pixel 9 Build/AP4A) AppleWebKit/537.36 Chrome/140.0 Mobile Safari/537.36"
    )
    assert device["device_type"] == "mobile"
    assert device["device_model"] == "Pixel 9"
    assert device["os"] == "Android"
    assert device["browser"] == "Chrome"

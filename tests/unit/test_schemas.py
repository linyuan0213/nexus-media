"""Pydantic Schema 单元测试"""

import pytest
from pydantic import ValidationError

from app.schemas.auth import LoginRequest, TokenPair, UserContext


class TestAuthSchemas:
    def test_login_request_valid(self):
        req = LoginRequest(username="admin", password="secret")
        assert req.username == "admin"
        assert req.password == "secret"
        assert req.remember is False

    def test_login_request_with_remember(self):
        req = LoginRequest(username="admin", password="secret", remember=True)
        assert req.remember is True

    def test_login_request_missing_password(self):
        with pytest.raises(ValidationError):
            LoginRequest(username="admin")  # type: ignore[call-arg]

    def test_token_pair_defaults(self):
        pair = TokenPair(access_token="abc", refresh_token="def", expires_in=3600)
        assert pair.token_type == "bearer"
        assert pair.expires_in == 3600

    def test_user_context_admin(self):
        ctx = UserContext(
            user_id=1,
            username="admin",
            level=0,
            permissions=["*"],
        )
        assert ctx.has_permission("anything") is True

    def test_user_context_permission_check(self):
        ctx = UserContext(
            user_id=2,
            username="user",
            level=1,
            permissions=["read", "write"],
        )
        assert ctx.has_permission("read") is True
        assert ctx.has_permission("delete") is False

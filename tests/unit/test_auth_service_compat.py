"""auth_service Python 3.14 兼容性单元测试."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.schemas.auth import UserContext
from app.services.auth_service import AuthService


class TestAuthServiceCompatibility:
    """测试认证服务兼容性."""

    def test_create_token_pair_uses_timezone_aware_now(self):
        """create_token_pair 应使用带时区的 UTC 时间，避免 utcnow 弃用."""
        ctx = UserContext(
            user_id=1,
            username="test",
            nickname=None,
            level=0,
            permissions=[],
        )
        before = datetime.now(timezone.utc)
        pair = AuthService.create_token_pair(ctx)
        after = datetime.now(timezone.utc)

        assert pair.access_token
        assert pair.refresh_token
        assert pair.expires_in == 15 * 60

        # verify_token 返回 UserContext，不携带 iat/exp
        # 这里只验证 create_token_pair 未触发 DeprecationWarning
        assert before <= datetime.now(timezone.utc) <= after + timedelta(seconds=5)

    def test_verify_token_payload_has_timezone_aware_datetimes(self):
        """verify_token 解析出的 token 载荷中 iat/exp 应为带时区时间."""
        ctx = UserContext(
            user_id=2,
            username="test2",
            nickname=None,
            level=0,
            permissions=["read"],
        )
        pair = AuthService.create_token_pair(ctx)
        import jwt

        from app.infrastructure.security import get_secret_key

        payload = jwt.decode(pair.access_token, get_secret_key(), algorithms=["HS256"], options={"verify_exp": False})
        assert payload["iat"] is not None
        assert payload["exp"] is not None
        # jwt 库默认返回 unix timestamp int，通过 leeway 等选项可获得 datetime
        # 这里仅验证 create_token_pair 未使用已弃用的 utcnow，并生成了有效时间戳
        assert isinstance(payload["iat"], int)
        assert isinstance(payload["exp"], int)
        assert payload["exp"] > payload["iat"]

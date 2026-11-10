"""
JWT 认证服务
提供 Access Token + Refresh Token 双令牌机制
"""

import base64
import io
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import pyotp
import qrcode
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from qrcode.image.svg import SvgPathImage

from app.core.exceptions import RepositoryError, ServiceError
from app.db.repositories.rbac.user_session_repository import RBACUserSessionRepository
from app.infrastructure.security import get_secret_key
from app.schemas.auth import TokenPair, UserContext
from app.utils.user_agent import describe_user_agent

# 密码加密上下文（Argon2）
pwd_context = PasswordHash([Argon2Hasher()])

# 配置项
_SECRET_KEY = get_secret_key()
_ALGORITHM = "HS256"
_ACCESS_TOKEN_EXPIRE_MINUTES = 15
_REFRESH_TOKEN_EXPIRE_DAYS = 7


class AuthService:
    """
    认证服务：处理 JWT Token 的签发、验证、刷新
    """

    def __init__(self, rbac_service: Any, session_repo: RBACUserSessionRepository | None = None):
        self._rbac_service = rbac_service
        self._session_repo = session_repo or RBACUserSessionRepository()

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """验证密码"""
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def hash_password(password: str) -> str:
        """加密密码"""
        return pwd_context.hash(password)

    def authenticate_detail(
        self,
        username: str,
        password: str,
        login_ip: str | None = None,
        user_agent: str | None = None,
        totp_code: str | None = None,
    ) -> tuple[UserContext | None, str]:
        """验证用户名密码/两步验证，返回 (上下文, 失败原因)."""
        success, result = self._rbac_service.authenticate_user(username, password, login_ip, user_agent, totp_code)
        if not success:
            reason = str(result or "")
            return None, reason if reason in {"TOTP_REQUIRED", "TOTP_INVALID"} else "invalid"

        user = result

        # 获取用户权限与角色码
        try:
            permissions = list(self._rbac_service.get_user_permissions(user.ID) or [])
            role_codes = list(self._rbac_service.get_user_role_codes(user.ID) or [])
        except (ServiceError, RepositoryError):
            permissions = []
            role_codes = []

        return (
            UserContext(
                user_id=user.ID,
                username=user.USERNAME,
                nickname=getattr(user, "NICKNAME", None),
                level=getattr(user, "LEVEL", 0) or 0,
                permissions=permissions,
                role_codes=role_codes,
            ),
            "ok",
        )

    def authenticate(
        self,
        username: str,
        password: str,
        login_ip: str | None = None,
        user_agent: str | None = None,
        totp_code: str | None = None,
    ) -> UserContext | None:
        """兼容旧调用：仅返回成功上下文."""
        return self.authenticate_detail(username, password, login_ip, user_agent, totp_code)[0]

    @staticmethod
    def create_token_pair(
        user_ctx: UserContext,
        *,
        session_id: str | None = None,
        refresh_jti: str | None = None,
    ) -> TokenPair:
        """创建 Access + Refresh Token 对；session_id 用于服务端吊销."""
        now = datetime.now(timezone.utc)
        session_id = session_id or user_ctx.session_id
        refresh_jti = refresh_jti or str(uuid.uuid4())

        # Access Token
        access_payload = {
            "sub": str(user_ctx.user_id),
            "user_id": user_ctx.user_id,
            "username": user_ctx.username,
            "nickname": user_ctx.nickname,
            "level": user_ctx.level,
            "permissions": user_ctx.permissions,
            "role_codes": user_ctx.role_codes,
            "iat": now,
            "exp": now + timedelta(minutes=_ACCESS_TOKEN_EXPIRE_MINUTES),
            "jti": str(uuid.uuid4()),
            "sid": session_id,
            "type": "access",
        }
        access_token = jwt.encode(access_payload, _SECRET_KEY, algorithm=_ALGORITHM)

        # Refresh Token（仅含 sub 和 jti）
        refresh_payload = {
            "sub": str(user_ctx.user_id),
            "jti": refresh_jti,
            "sid": session_id,
            "iat": now,
            "exp": now + timedelta(days=_REFRESH_TOKEN_EXPIRE_DAYS),
            "type": "refresh",
        }
        refresh_token = jwt.encode(refresh_payload, _SECRET_KEY, algorithm=_ALGORITHM)

        return TokenPair(
            access_token=access_token, refresh_token=refresh_token, expires_in=_ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )

    def create_session_pair(
        self,
        user_ctx: UserContext,
        *,
        login_ip: str | None,
        user_agent: str | None,
    ) -> TokenPair:
        """创建服务端会话和 Token 对."""
        session_id = uuid.uuid4().hex
        refresh_jti = uuid.uuid4().hex
        expires_at = datetime.now() + timedelta(days=_REFRESH_TOKEN_EXPIRE_DAYS)
        user_ctx.session_id = session_id
        self._session_repo.create_session(
            session_id,
            user_ctx.user_id,
            refresh_jti,
            device=describe_user_agent(user_agent),
            login_ip=login_ip,
            user_agent=user_agent,
            expires_at=expires_at,
        )
        return self.create_token_pair(user_ctx, session_id=session_id, refresh_jti=refresh_jti)

    def verify_token_with_session(self, token: str) -> tuple[UserContext | None, str]:
        """验证 Access Token，并检查服务端会话未吊销."""
        user_ctx, reason = self.verify_token_detail(token)
        if user_ctx is None:
            return None, reason
        if user_ctx.session_id and self._session_repo.get_active_session(user_ctx.session_id, user_ctx.user_id) is None:
            return None, "revoked"
        return user_ctx, "ok"

    def list_sessions(self, user_id: int) -> list[dict[str, Any]]:
        return self._session_repo.list_sessions(user_id)

    def revoke_session(self, session_id: str, user_id: int | None = None, *, reason: str = "logout") -> bool:
        return self._session_repo.revoke_session(session_id, user_id=user_id, reason=reason)

    def revoke_other_sessions(self, user_id: int, keep_session_id: str) -> int:
        return self._session_repo.revoke_other_sessions(user_id, keep_session_id)

    def totp_status(self, user_id: int) -> dict[str, Any]:
        user = self._rbac_service.get_user_by_id(user_id)
        return {
            "enabled": bool(getattr(user, "TOTP_ENABLED", 0)) if user else False,
            "configured": bool(getattr(user, "TOTP_SECRET", "")) if user else False,
        }

    def begin_totp_setup(self, user_id: int) -> tuple[bool, dict[str, str]]:
        user = self._rbac_service.get_user_by_id(user_id)
        if not user:
            return False, {"message": "用户不存在"}
        if getattr(user, "TOTP_ENABLED", 0):
            return False, {"message": "两步验证已启用"}
        secret = pyotp.random_base32()
        self._rbac_service.update_user(
            user_id,
            TOTP_SECRET=secret,
            TOTP_ENABLED=0,
            TOTP_RECOVERY_CODES=None,
        )
        uri = pyotp.TOTP(secret).provisioning_uri(name=user.USERNAME, issuer_name="Nexus Media")
        buffer = io.BytesIO()
        qrcode.make(uri, image_factory=SvgPathImage, border=2).save(buffer)
        qr_data_uri = "data:image/svg+xml;base64," + base64.b64encode(buffer.getvalue()).decode()
        return True, {"secret": secret, "uri": uri, "qr_data_uri": qr_data_uri}

    def enable_totp(self, user_id: int, code: str) -> tuple[bool, dict[str, Any]]:
        user = self._rbac_service.get_user_by_id(user_id)
        if not user:
            return False, {"message": "用户不存在"}
        secret = str(getattr(user, "TOTP_SECRET", "") or "")
        if not secret or not pyotp.TOTP(secret).verify(str(code or "").strip(), valid_window=1):
            return False, {"message": "验证码错误"}
        recovery_codes = [secrets.token_hex(4) for _ in range(8)]
        hashed = [self.hash_password(item) for item in recovery_codes]
        self._rbac_service.update_user(
            user_id,
            TOTP_ENABLED=1,
            TOTP_RECOVERY_CODES=json.dumps(hashed),
        )
        return True, {"recovery_codes": recovery_codes}

    def disable_totp(self, user_id: int, password: str, code: str) -> tuple[bool, str]:
        user = self._rbac_service.get_user_by_id(user_id)
        if not user or not self.verify_password(password, user.PASSWORD_HASH or ""):
            return False, "密码错误"
        secret = str(getattr(user, "TOTP_SECRET", "") or "")
        if not secret or not pyotp.TOTP(secret).verify(str(code or "").strip(), valid_window=1):
            return False, "验证码错误"
        self._rbac_service.update_user(
            user_id,
            TOTP_ENABLED=0,
            TOTP_SECRET=None,
            TOTP_RECOVERY_CODES=None,
        )
        return True, "两步验证已关闭"

    def refresh_access_token(
        self,
        refresh_token: str,
        *,
        login_ip: str | None = None,
        user_agent: str | None = None,
    ) -> TokenPair | None:
        """使用 Refresh Token 换取新的 Token 对，并轮换服务端会话."""
        try:
            payload = jwt.decode(refresh_token, _SECRET_KEY, algorithms=[_ALGORITHM])
            if payload.get("type") != "refresh":
                return None

            user_id = int(payload.get("sub") or 0)
            session_id = str(payload.get("sid") or "")
            refresh_jti = str(payload.get("jti") or "")
            if not user_id or not refresh_jti:
                return None

            # 旧版 Refresh Token 没有 sid：平滑升级为新的服务端会话。
            if session_id:
                session = self._session_repo.get_active_session(session_id, user_id)
                if session is None or session.get("refresh_jti") != refresh_jti:
                    return None

            # 重新获取用户信息
            user = self._rbac_service.get_user_by_id(user_id)
            if not user:
                return None

            # 构建用户上下文
            try:
                permissions = list(self._rbac_service.get_user_permissions(user_id) or [])
                role_codes = list(self._rbac_service.get_user_role_codes(user_id) or [])
            except (ServiceError, RepositoryError):
                permissions = []
                role_codes = []

            level = getattr(user, "LEVEL", 0) or 0

            ctx = UserContext(
                user_id=user_id,
                username=getattr(user, "USERNAME", ""),
                nickname=getattr(user, "NICKNAME", None) or None,
                level=level,
                permissions=permissions,
                role_codes=role_codes,
                session_id=session_id,
            )
            if not session_id:
                return self.create_session_pair(ctx, login_ip=login_ip, user_agent=user_agent)
            new_jti = uuid.uuid4().hex
            self._session_repo.touch_session(session_id, refresh_jti=new_jti, login_ip=login_ip)
            return self.create_token_pair(ctx, session_id=session_id, refresh_jti=new_jti)

        except (jwt.InvalidTokenError, ValueError):
            return None

    @staticmethod
    def verify_token_detail(token: str) -> tuple[UserContext | None, str]:
        """验证 Access Token，返回 (上下文, 状态)；状态区分 expired/invalid/ok."""
        try:
            payload = jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])
        except jwt.ExpiredSignatureError:
            return None, "expired"
        except (jwt.InvalidTokenError, ValueError):
            return None, "invalid"
        if payload.get("type") != "access":
            return None, "invalid"
        return (
            UserContext(
                user_id=payload.get("user_id", 0),
                username=payload.get("username", ""),
                nickname=payload.get("nickname", None),
                level=payload.get("level", 0),
                permissions=payload.get("permissions", []),
                role_codes=payload.get("role_codes", []),
                session_id=payload.get("sid"),
            ),
            "ok",
        )

    @staticmethod
    def verify_token(token: str) -> UserContext | None:
        """验证 Access Token，返回用户上下文."""
        return AuthService.verify_token_detail(token)[0]

    @staticmethod
    def revoke_token(jti: str) -> None:
        """
        撤销 Token（将 jti 加入黑名单）
        当前为基础实现，P4 可配合 Redis 实现分布式黑名单
        """

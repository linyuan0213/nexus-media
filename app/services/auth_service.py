# -*- coding: utf-8 -*-
"""
JWT 认证服务
提供 Access Token + Refresh Token 双令牌机制
"""
import uuid
from datetime import datetime, timedelta
from typing import Optional

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.schemas.auth import TokenPair, UserContext
from app.services.rbac_service import rbac_service
from app.utils.security import get_secret_key

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

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """验证密码"""
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def hash_password(password: str) -> str:
        """加密密码"""
        return pwd_context.hash(password)

    @staticmethod
    def authenticate(username: str, password: str) -> Optional[UserContext]:
        """
        验证用户名密码，返回用户上下文
        """
        success, result = rbac_service.authenticate_user(username, password)
        if not success:
            return None

        user = result

        # 获取用户权限
        try:
            permissions = rbac_service.get_user_permissions(user.ID)
            permissions = list(permissions) if permissions else []
        except Exception:
            permissions = []

        level = getattr(user, 'LEVEL', 0) or 0
        is_superadmin = getattr(user, 'IS_SUPERADMIN', 0) == 1

        return UserContext(
            user_id=user.ID,
            username=user.USERNAME,
            nickname=getattr(user, 'NICKNAME', None) or None,
            level=level,
            permissions=permissions,
            is_superadmin=is_superadmin
        )

    @staticmethod
    def create_token_pair(user_ctx: UserContext) -> TokenPair:
        """
        创建 Access + Refresh Token 对
        """
        now = datetime.utcnow()

        # Access Token
        access_payload = {
            "sub": str(user_ctx.user_id),
            "user_id": user_ctx.user_id,
            "username": user_ctx.username,
            "nickname": user_ctx.nickname,
            "level": user_ctx.level,
            "permissions": user_ctx.permissions,
            "is_superadmin": user_ctx.is_superadmin,
            "iat": now,
            "exp": now + timedelta(minutes=_ACCESS_TOKEN_EXPIRE_MINUTES),
            "jti": str(uuid.uuid4()),
            "type": "access"
        }
        access_token = jwt.encode(access_payload, _SECRET_KEY, algorithm=_ALGORITHM)

        # Refresh Token（仅含 sub 和 jti）
        refresh_payload = {
            "sub": str(user_ctx.user_id),
            "jti": str(uuid.uuid4()),
            "iat": now,
            "exp": now + timedelta(days=_REFRESH_TOKEN_EXPIRE_DAYS),
            "type": "refresh"
        }
        refresh_token = jwt.encode(refresh_payload, _SECRET_KEY, algorithm=_ALGORITHM)

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=_ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )

    @staticmethod
    def refresh_access_token(refresh_token: str) -> Optional[TokenPair]:
        """
        使用 Refresh Token 换取新的 Token 对
        """
        try:
            payload = jwt.decode(refresh_token, _SECRET_KEY, algorithms=[_ALGORITHM])
            if payload.get("type") != "refresh":
                return None

            user_id = int(payload.get("sub"))
            if not user_id:
                return None

            # 重新获取用户信息
            user = rbac_service.get_user_by_id(user_id)
            if not user:
                return None

            # 构建用户上下文
            try:
                permissions = rbac_service.get_user_permissions(user_id)
                permissions = list(permissions) if permissions else []
            except Exception:
                permissions = []

            level = getattr(user, 'LEVEL', 0) or 0
            is_superadmin = getattr(user, 'IS_SUPERADMIN', 0) == 1

            ctx = UserContext(
                user_id=user_id,
                username=getattr(user, 'USERNAME', ''),
                nickname=getattr(user, 'NICKNAME', None) or None,
                level=level,
                permissions=permissions,
                is_superadmin=is_superadmin
            )
            return AuthService.create_token_pair(ctx)

        except (jwt.InvalidTokenError, ValueError):
            return None

    @staticmethod
    def verify_token(token: str) -> Optional[UserContext]:
        """
        验证 Access Token，返回用户上下文
        """
        try:
            payload = jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])
            if payload.get("type") != "access":
                return None

            return UserContext(
                user_id=payload.get("user_id", 0),
                username=payload.get("username", ""),
                nickname=payload.get("nickname", None),
                level=payload.get("level", 0),
                permissions=payload.get("permissions", []),
                is_superadmin=payload.get("is_superadmin", False)
            )
        except (jwt.InvalidTokenError, ValueError):
            return None

    @staticmethod
    def revoke_token(jti: str) -> None:
        """
        撤销 Token（将 jti 加入黑名单）
        当前为基础实现，P4 可配合 Redis 实现分布式黑名单
        """
        pass

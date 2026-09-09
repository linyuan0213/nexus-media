"""
JWT 认证相关 Schema
"""

from datetime import datetime

from pydantic import BaseModel

SUPERADMIN_ROLE_CODE = "superadmin"


class TokenPayload(BaseModel):
    """JWT Payload 结构"""

    sub: str  # 用户唯一标识
    user_id: int  # 用户 ID
    username: str  # 用户名
    level: int  # 用户等级
    permissions: list[str]  # 权限列表
    role_codes: list[str] = []  # 角色码列表（前端展示用，后端判定不依赖）
    iat: datetime  # 签发时间
    exp: datetime  # 过期时间
    jti: str  # Token 唯一标识


class TokenPair(BaseModel):
    """登录返回的 Token 对"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # Access Token 有效期（秒）


class UserContext(BaseModel):
    """从 Token 解析的用户上下文"""

    user_id: int
    username: str
    nickname: str | None = None
    level: int
    permissions: list[str]
    role_codes: list[str] = []

    @property
    def is_superadmin(self) -> bool:
        return SUPERADMIN_ROLE_CODE in self.role_codes

    def has_permission(self, permission_code: str) -> bool:
        return "*" in self.permissions or permission_code in self.permissions


def system_user_context() -> UserContext:
    """系统上下文：后台任务/事件 handler 等无用户路径使用，具全部数据可见性。"""
    return UserContext(
        user_id=0,
        username="system",
        level=0,
        permissions=[],
        role_codes=[SUPERADMIN_ROLE_CODE],
    )


class LoginRequest(BaseModel):
    """登录请求"""

    username: str
    password: str
    remember: bool = False


class LoginResponse(BaseModel):
    """登录响应"""

    code: int
    success: bool
    message: str
    data: TokenPair | None = None


class RefreshTokenRequest(BaseModel):
    """刷新 Token 请求（也可通过 Cookie 传递）"""

    refresh_token: str | None = None

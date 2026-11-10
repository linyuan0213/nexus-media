"""
JWT 认证路由
提供登录、刷新 Token、登出、获取当前用户信息
"""

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.security import OAuth2PasswordRequestForm

from api.deps import get_auth_service, get_current_user, get_rbac_service
from app.core.error_codes import ErrorCode
from app.core.exceptions import AuthError
from app.core.settings import AppSettings
from app.schemas.auth import LoginResponse, TOTPCodeRequest, TOTPDisableRequest, UserContext
from app.schemas.common import CommonResponse
from app.services.auth_service import AuthService
from app.services.rbac_service import RBACService

_settings = AppSettings()

router = APIRouter()


def _request_meta(request: Request) -> tuple[str | None, str | None]:
    forwarded = request.headers.get("x-forwarded-for") or ""
    ip = forwarded.split(",")[0].strip() or (request.client.host if request.client else None)
    return ip, request.headers.get("user-agent")


@router.post("/login", response_model=LoginResponse)
def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    totp_code: str | None = Form(None),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    用户登录，返回 JWT Token 对。
    Refresh Token 通过 HttpOnly Cookie 返回。
    """
    login_ip, user_agent = _request_meta(request)
    user_ctx, reason = auth_service.authenticate_detail(
        form_data.username,
        form_data.password,
        login_ip,
        user_agent,
        totp_code,
    )
    if not user_ctx:
        if reason == "TOTP_REQUIRED":
            raise AuthError("请输入两步验证码", errcode=ErrorCode.TOTP_REQUIRED, http_status=401)
        if reason == "TOTP_INVALID":
            raise AuthError("两步验证码错误", errcode=ErrorCode.TOTP_INVALID, http_status=401)
        raise AuthError(
            "用户名或密码错误",
            errcode=ErrorCode.PASSWORD_INCORRECT,
            http_status=401,
            headers={"WWW-Authenticate": "Bearer"},
        )

    tokens = auth_service.create_session_pair(user_ctx, login_ip=login_ip, user_agent=user_agent)

    # 将 Refresh Token 写入 HttpOnly Cookie
    response.set_cookie(
        key="refresh_token",
        value=tokens.refresh_token,
        httponly=True,
        secure=_settings.app.cookie_secure,
        samesite="lax",
        max_age=7 * 24 * 3600,  # 7 天
    )

    return LoginResponse(code=0, success=True, message="登录成功", data=tokens)


@router.post("/refresh", response_model=LoginResponse)
def refresh_token(
    request: Request,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    使用 Refresh Token 换取新的 Token 对（Token 轮换机制）。
    """
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise AuthError(
            "未提供 Refresh Token",
            errcode=ErrorCode.REFRESH_TOKEN_INVALID,
            http_status=401,
        )

    login_ip, user_agent = _request_meta(request)
    tokens = auth_service.refresh_access_token(refresh_token, login_ip=login_ip, user_agent=user_agent)
    if not tokens:
        raise AuthError(
            "Refresh Token 无效或已过期",
            errcode=ErrorCode.REFRESH_TOKEN_INVALID,
            http_status=401,
        )

    # Token 轮换：同时刷新 Refresh Token
    response.set_cookie(
        key="refresh_token",
        value=tokens.refresh_token,
        httponly=True,
        secure=_settings.app.cookie_secure,
        samesite="lax",
        max_age=7 * 24 * 3600,
    )

    return LoginResponse(code=0, success=True, message="Token 刷新成功", data=tokens)


@router.post("/logout", response_model=CommonResponse, summary="用户登出")
async def logout(
    response: Response,
    user: UserContext = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """登出：撤销当前服务端会话并清除 Refresh Token Cookie."""
    if user.session_id:
        auth_service.revoke_session(user.session_id, user.user_id, reason="logout")
    response.delete_cookie("refresh_token")
    return {"code": 0, "data": True, "message": "已登出"}


@router.get("/sessions", response_model=CommonResponse, summary="获取登录设备会话")
async def list_sessions(
    user: UserContext = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    sessions = auth_service.list_sessions(user.user_id)
    for item in sessions:
        item.pop("refresh_jti", None)
        item["is_current"] = item.get("session_id") == user.session_id
        item["is_active"] = not item.get("revoked_at")
    # 当前设备固定置顶，其余保持最近活跃倒序。
    sessions.sort(key=lambda item: item.get("last_seen_at") or "", reverse=True)
    sessions.sort(key=lambda item: 0 if item.get("is_current") else 1)
    return {"code": 0, "data": sessions, "message": "ok"}


@router.post("/sessions/{session_id}/revoke", response_model=CommonResponse, summary="退出指定登录设备")
async def revoke_session(
    session_id: str,
    user: UserContext = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    if not auth_service.revoke_session(session_id, user.user_id, reason="user_revoke"):
        raise AuthError("会话不存在或已失效", errcode=ErrorCode.RESOURCE_NOT_FOUND, http_status=404)
    return {"code": 0, "data": True, "message": "该设备已退出登录"}


@router.post("/sessions/revoke-others", response_model=CommonResponse, summary="退出其他登录设备")
async def revoke_other_sessions(
    user: UserContext = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    if not user.session_id:
        raise AuthError("当前登录会话无效", errcode=ErrorCode.UNAUTHORIZED, http_status=401)
    count = auth_service.revoke_other_sessions(user.user_id, user.session_id)
    return {"code": 0, "data": {"revoked": count}, "message": "其他设备已退出登录"}


@router.get("/totp/status", response_model=CommonResponse, summary="获取两步验证状态")
async def totp_status(
    user: UserContext = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    return {"code": 0, "data": auth_service.totp_status(user.user_id), "message": "ok"}


@router.post("/totp/setup", response_model=CommonResponse, summary="开始绑定两步验证")
async def totp_setup(
    user: UserContext = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    ok, data = auth_service.begin_totp_setup(user.user_id)
    if not ok:
        return {"code": 1, "data": None, "message": data.get("message", "操作失败")}
    return {"code": 0, "data": data, "message": "请使用验证器扫码并输入验证码"}


@router.post("/totp/enable", response_model=CommonResponse, summary="确认启用两步验证")
async def totp_enable(
    body: TOTPCodeRequest,
    user: UserContext = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    ok, data = auth_service.enable_totp(user.user_id, body.code)
    if not ok:
        return {"code": 1, "data": None, "message": data.get("message", "操作失败")}
    return {"code": 0, "data": data, "message": "两步验证已启用"}


@router.post("/totp/disable", response_model=CommonResponse, summary="关闭两步验证")
async def totp_disable(
    body: TOTPDisableRequest,
    user: UserContext = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    ok, message = auth_service.disable_totp(user.user_id, body.password, body.code)
    if not ok:
        return {"code": 1, "data": None, "message": message}
    return {"code": 0, "data": True, "message": message}


@router.get("/me", response_model=CommonResponse, summary="获取当前用户信息")
async def get_current_user_info(
    user: UserContext = Depends(get_current_user),
    rbac_service: RBACService = Depends(get_rbac_service),
):
    """
    获取当前登录用户信息。
    """
    if isinstance(user, str):
        return {
            "code": 0,
            "data": {
                "username": user,
                "user_id": 0,
                "level": 0,
                "permissions": [],
                "roles": [],
            },
        }
    roles = rbac_service.get_user_roles(user.user_id)
    user_detail = rbac_service.get_user_by_id(user.user_id)
    avatar = user_detail.AVATAR if user_detail else None
    email = user_detail.EMAIL if user_detail else None
    return {
        "code": 0,
        "data": {
            "user_id": user.user_id,
            "username": user.username,
            "nickname": user.nickname,
            "email": email,
            "avatar": avatar,
            "level": user.level,
            "permissions": user.permissions,
            # 超管按角色代码判定（角色代码不可通过接口修改）
            "is_superadmin": any(r.role_code == "superadmin" for r in roles) if roles else False,
            "is_default_password": rbac_service.is_default_password(user.user_id),
            "roles": [role.role_name for role in roles] if roles else [],
        },
    }

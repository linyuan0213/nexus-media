# -*- coding: utf-8 -*-
"""
JWT 认证路由
提供登录、刷新 Token、登出、获取当前用户信息
"""
from fastapi import APIRouter, Response, Request, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordRequestForm

from app.schemas.auth import TokenPair, UserContext, LoginResponse
from app.services.auth_service import AuthService
from api.deps import get_current_user, get_current_user_optional

router = APIRouter(prefix="/api/auth", tags=["authentication"])


@router.post("/login", response_model=LoginResponse)
async def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends()
):
    """
    用户登录，返回 JWT Token 对。
    Refresh Token 通过 HttpOnly Cookie 返回。
    """
    user_ctx = AuthService.authenticate(form_data.username, form_data.password)
    if not user_ctx:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"}
        )

    tokens = AuthService.create_token_pair(user_ctx)

    # 将 Refresh Token 写入 HttpOnly Cookie
    response.set_cookie(
        key="refresh_token",
        value=tokens.refresh_token,
        httponly=True,
        secure=False,  # 生产环境改为 True
        samesite="lax",
        max_age=7 * 24 * 3600  # 7 天
    )

    return LoginResponse(
        code=0,
        success=True,
        message="登录成功",
        data=tokens
    )


@router.post("/refresh", response_model=LoginResponse)
async def refresh_token(request: Request, response: Response):
    """
    使用 Refresh Token 换取新的 Token 对（Token 轮换机制）。
    """
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供 Refresh Token"
        )

    tokens = AuthService.refresh_access_token(refresh_token)
    if not tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh Token 无效或已过期"
        )

    # Token 轮换：同时刷新 Refresh Token
    response.set_cookie(
        key="refresh_token",
        value=tokens.refresh_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=7 * 24 * 3600
    )

    return LoginResponse(
        code=0,
        success=True,
        message="Token 刷新成功",
        data=tokens
    )


@router.post("/logout")
async def logout(response: Response, user: UserContext = Depends(get_current_user)):
    """
    登出，清除 Refresh Token Cookie。
    """
    response.delete_cookie("refresh_token")
    return {"code": 0, "success": True, "message": "已登出"}


@router.get("/me")
async def get_current_user_info(user: UserContext = Depends(get_current_user)):
    """
    获取当前登录用户信息。
    兼容测试中的字符串 override（绞杀期过渡）。
    """
    if isinstance(user, str):
        return {"username": user, "user_id": 0, "level": 0,
                "permissions": [], "is_superadmin": False}
    return user

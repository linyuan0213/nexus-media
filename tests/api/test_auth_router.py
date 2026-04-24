# -*- coding: utf-8 -*-
"""
JWT 认证路由测试
"""
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.deps import get_current_user

client = TestClient(app)


class TestAuthRouter:
    """认证路由测试"""

    def setup_method(self):
        # 保存并移除全局 auth override（避免其他测试文件的 lambda: "testuser" 污染）
        self._saved_override = app.dependency_overrides.pop(get_current_user, None)

    def teardown_method(self):
        # 恢复全局 auth override
        if self._saved_override is not None:
            app.dependency_overrides[get_current_user] = self._saved_override

    @patch("api.routers.auth.AuthService.authenticate")
    def test_login_success(self, mock_auth):
        """测试登录成功"""
        from app.schemas.auth import UserContext
        mock_auth.return_value = UserContext(
            user_id=1, username="admin", level=1,
            permissions=["*"], is_superadmin=True
        )

        resp = client.post(
            "/api/auth/login",
            data={"username": "admin", "password": "admin"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert data["success"] is True
        assert "access_token" in data["data"]
        assert "refresh_token" in data["data"]
        assert "refresh_token" in resp.cookies

    @patch("api.routers.auth.AuthService.authenticate")
    def test_login_failure(self, mock_auth):
        """测试登录失败"""
        mock_auth.return_value = None

        resp = client.post(
            "/api/auth/login",
            data={"username": "wrong", "password": "wrong"}
        )
        assert resp.status_code == 401

    def test_me_without_auth(self):
        """测试未认证访问 /me"""
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

    @patch("api.routers.auth.AuthService.authenticate")
    def test_me_with_auth(self, mock_auth):
        """测试认证后访问 /me"""
        from app.schemas.auth import UserContext
        mock_auth.return_value = UserContext(
            user_id=1, username="testuser", level=0,
            permissions=[], is_superadmin=False
        )

        # 登录
        login_resp = client.post(
            "/api/auth/login",
            data={"username": "testuser", "password": "testpass"}
        )
        token = login_resp.json()["data"]["access_token"]

        # 访问 /me
        resp = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "testuser"
        assert data["user_id"] == 1

    @patch("api.routers.auth.AuthService.authenticate")
    @patch("api.routers.auth.AuthService.refresh_access_token")
    def test_refresh_token(self, mock_refresh, mock_auth):
        """测试刷新 Token"""
        from app.schemas.auth import UserContext, TokenPair
        mock_auth.return_value = UserContext(
            user_id=1, username="admin", level=1,
            permissions=["*"], is_superadmin=True
        )
        mock_refresh.return_value = TokenPair(
            access_token="new_access_token",
            refresh_token="new_refresh_token",
            expires_in=900
        )

        # 登录获取初始 Token
        login_resp = client.post(
            "/api/auth/login",
            data={"username": "admin", "password": "admin"}
        )
        assert login_resp.status_code == 200

        # 刷新 Token（携带 Cookie）
        refresh_resp = client.post(
            "/api/auth/refresh",
            cookies=login_resp.cookies
        )
        assert refresh_resp.status_code == 200
        data = refresh_resp.json()
        assert data["code"] == 0
        assert data["data"]["access_token"] == "new_access_token"

    @patch("api.routers.auth.AuthService.authenticate")
    def test_logout(self, mock_auth):
        """测试登出"""
        from app.schemas.auth import UserContext
        mock_auth.return_value = UserContext(
            user_id=1, username="admin", level=1,
            permissions=["*"], is_superadmin=True
        )

        # 登录
        login_resp = client.post(
            "/api/auth/login",
            data={"username": "admin", "password": "admin"}
        )
        token = login_resp.json()["data"]["access_token"]

        # 登出
        resp = client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @patch("api.deps.AuthService.verify_token")
    def test_jwt_auth_flow(self, mock_verify):
        """测试完整 JWT 认证流程"""
        from app.schemas.auth import UserContext
        mock_verify.return_value = UserContext(
            user_id=1, username="jwtuser", level=0,
            permissions=["read"], is_superadmin=False
        )

        # 使用 JWT 访问需要认证的接口
        resp = client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer fake_jwt_token"}
        )
        assert resp.status_code == 200
        assert resp.json()["username"] == "jwtuser"

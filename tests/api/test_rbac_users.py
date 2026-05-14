"""
RBAC 用户管理路由测试
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from api.deps import get_current_user
from api.main import app

client = TestClient(app)


class TestRbacUsersRouter:
    """用户管理路由测试"""

    def setup_method(self):
        self._saved_override = app.dependency_overrides.pop(get_current_user, None)

    def teardown_method(self):
        if self._saved_override is not None:
            app.dependency_overrides[get_current_user] = self._saved_override

    @patch("app.services.rbac_service.RbacService.get_users")
    def test_get_users(self, mock_get_users):
        """测试获取用户列表"""
        mock_get_users.return_value = [
            {
                "id": 1,
                "username": "admin",
                "nickname": "管理员",
                "email": "admin@example.com",
                "status": 1,
                "roles": [{"id": 1, "role_name": "管理员"}],
                "last_login_at": "2026-04-25 10:00:00",
            }
        ]

        resp = client.post("/api/rbac/users", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert len(data["data"]) == 1
        assert data["data"][0]["username"] == "admin"

    @patch("app.services.rbac_service.RbacService.create_user")
    def test_create_user(self, mock_create):
        """测试创建用户"""
        mock_create.return_value = {"id": 2, "username": "testuser"}

        resp = client.post(
            "/api/rbac/users/create",
            json={
                "username": "testuser",
                "password": "testpass",
                "nickname": "测试用户",
                "email": "test@example.com",
                "role_ids": [2],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0

    @patch("app.services.rbac_service.RbacService.update_user")
    def test_update_user(self, mock_update):
        """测试更新用户"""
        mock_update.return_value = {"id": 1, "nickname": "新昵称"}

        resp = client.post(
            "/api/rbac/users/update",
            json={
                "id": 1,
                "nickname": "新昵称",
                "status": 1,
                "role_ids": [1],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0

    @patch("app.services.rbac_service.RbacService.delete_user")
    def test_delete_user(self, mock_delete):
        """测试删除用户"""
        mock_delete.return_value = True

        resp = client.post("/api/rbac/users/delete", json={"id": 2})
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0

    @patch("app.services.rbac_service.RbacService.reset_password")
    def test_reset_password(self, mock_reset):
        """测试重置密码"""
        mock_reset.return_value = True

        resp = client.post(
            "/api/rbac/users/reset_password",
            json={"user_id": 2, "new_password": "newpass123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0

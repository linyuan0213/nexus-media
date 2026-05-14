from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.deps import get_current_user
from api.main import app

client = TestClient(app)
app.dependency_overrides[get_current_user] = lambda: "testuser"


class TestRbacRouter:

    # ----- rbac_service endpoints -----

    @patch("api.routers.rbac.rbac_service")
    def test_create_menu_success(self, mock_rbac):
        menu = MagicMock()
        menu.to_dict.return_value = {"id": 1, "name": "menu1"}
        mock_rbac.create_menu.return_value = (True, menu)

        resp = client.post("/api/rbac/create_menu", json={
            "menu_name": "menu1", "menu_code": "m1"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["id"] == 1

    def test_create_menu_fail_validation(self):
        resp = client.post("/api/rbac/create_menu", json={
            "menu_name": "", "menu_code": ""
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    @patch("api.routers.rbac.rbac_service")
    def test_create_role_success(self, mock_rbac):
        role = MagicMock()
        role.to_dict.return_value = {"id": 1, "name": "role1"}
        mock_rbac.create_role.return_value = (True, role)

        resp = client.post("/api/rbac/create_role", json={
            "role_name": "role1", "role_code": "r1"
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @patch("api.routers.rbac.rbac_service")
    def test_delete_menu(self, mock_rbac):
        mock_rbac.delete_menu.return_value = (True, "删除成功")

        resp = client.post("/api/rbac/delete_menu", json={"id": 1})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @patch("api.routers.rbac.rbac_service")
    def test_delete_role(self, mock_rbac):
        mock_rbac.delete_role.return_value = (True, "删除成功")

        resp = client.post("/api/rbac/delete_role", json={"id": 1})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @patch("api.routers.rbac.rbac_service")
    def test_get_menu(self, mock_rbac):
        menu = MagicMock()
        menu.to_dict.return_value = {"id": 1}
        mock_rbac.menu_repo.get_menu_by_id.return_value = menu

        resp = client.post("/api/rbac/get_menu", json={"id": 1})
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert resp.json()["data"]["id"] == 1

    @patch("api.routers.rbac.rbac_service")
    def test_get_menu_not_found(self, mock_rbac):
        mock_rbac.menu_repo.get_menu_by_id.return_value = None

        resp = client.post("/api/rbac/get_menu", json={"id": 99})
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    @patch("api.routers.rbac.rbac_service")
    def test_get_role(self, mock_rbac):
        role = MagicMock()
        role.to_dict.return_value = {"id": 1}
        mock_rbac.get_role_by_id.return_value = role

        resp = client.post("/api/rbac/get_role", json={"id": 1})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @patch("api.routers.rbac.rbac_service")
    def test_update_menu(self, mock_rbac):
        mock_rbac.update_menu.return_value = (True, "更新成功")

        resp = client.post("/api/rbac/update_menu", json={
            "id": 1, "menu_name": "new name"
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @patch("api.routers.rbac.rbac_service")
    def test_update_menu_sort(self, mock_rbac):
        mock_rbac.update_menu.return_value = (True, "ok")

        resp = client.post("/api/rbac/update_menu_sort", json={
            "menu_orders": [
                {"id": 1, "sort_order": 0, "parent_id": None},
                {"id": 2, "sort_order": 1, "parent_id": 1}
            ]
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert "2" in resp.json()["message"]

    @patch("api.routers.rbac.rbac_service")
    def test_update_role(self, mock_rbac):
        mock_rbac.update_role.return_value = (True, "更新成功")

        resp = client.post("/api/rbac/update_role", json={
            "id": 1, "role_name": "new", "permission_ids": [1, 2], "menu_ids": [3]
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        mock_rbac.assign_permissions_to_role.assert_called_once_with(1, [1, 2])
        mock_rbac.assign_menus_to_role.assert_called_once_with(1, [3])

    @patch("api.routers.rbac.rbac_service")
    def test_update_user(self, mock_rbac):
        mock_rbac.update_user.return_value = (True, "更新成功")

        resp = client.post("/api/rbac/update_user", json={
            "id": 1, "email": "a@b.com", "role_ids": [1]
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        mock_rbac.assign_roles_to_user.assert_called_once_with(1, [1])

    # ----- User class endpoints -----

    @patch("api.routers.rbac.rbac_service")
    def test_create_user_success(self, mock_rbac):
        user = MagicMock()
        user.to_dict.return_value = {"id": 1, "username": "test"}
        mock_rbac.create_user.return_value = (True, user)

        resp = client.post("/api/rbac/create_user", json={
            "username": "test", "password": "123456"
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @patch("api.routers.rbac.rbac_service")
    def test_delete_user(self, mock_rbac):
        mock_rbac.delete_user.return_value = (True, "删除成功")

        resp = client.post("/api/rbac/delete_user", json={"id": 1})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @patch("api.routers.rbac.rbac_service")
    def test_get_user(self, mock_rbac):
        user = MagicMock()
        user.to_dict.return_value = {"id": 1, "username": "test"}
        mock_rbac.get_user_by_id.return_value = user

        resp = client.post("/api/rbac/get_user", json={"id": 1})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @patch("api.routers.rbac.rbac_service")
    def test_reset_password(self, mock_rbac):
        mock_rbac.reset_password.return_value = (True, "重置成功")

        resp = client.post("/api/rbac/reset_password", json={
            "user_id": 1, "new_password": "newpass"
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @patch("api.routers.rbac.rbac_service")
    @patch("api.routers.rbac._get_user_id_from_ctx")
    def test_get_top_menus(self, mock_get_uid, mock_rbac):
        mock_get_uid.return_value = 1
        menu = MagicMock()
        menu.MENU_NAME = "Home"
        menu.PATH = "/home"
        menu.ICON = "home"
        menu.MENU_LEVEL = 1
        mock_rbac.get_user_menus.return_value = [menu]

        resp = client.post("/api/rbac/get_top_menus", json={})
        assert resp.status_code == 200
        assert resp.json()["menus"][0]["name"] == "Home"

    @patch("api.routers.rbac.rbac_service")
    @patch("api.routers.rbac._get_user_id_from_ctx")
    def test_get_user_menus(self, mock_get_uid, mock_rbac):
        mock_get_uid.return_value = 1
        parent = MagicMock()
        parent.ID = 1
        parent.MENU_NAME = "Home"
        parent.PATH = "/home"
        parent.ICON = "home"
        parent.MENU_LEVEL = 1
        parent.PARENT_ID = None

        child = MagicMock()
        child.ID = 2
        child.MENU_NAME = "Sub"
        child.PATH = "/sub"
        child.ICON = ""
        child.MENU_LEVEL = 2
        child.PARENT_ID = 1

        mock_rbac.get_user_menus.return_value = [parent, child]

        resp = client.post("/api/rbac/get_user_menus", json={
            "ignore": ["admin"]
        })
        assert resp.status_code == 200
        assert resp.json()["menus"][0]["name"] == "Home"
        assert resp.json()["level"] == 0  # 测试使用 str override，level 默认为 0

    @patch("api.routers.rbac.rbac_service")
    def test_get_users(self, mock_rbac):
        user = MagicMock()
        user.ID = 1
        user.USERNAME = "test"
        user.NICKNAME = "t"
        user.EMAIL = "a@b.com"
        user.STATUS = 1
        role = MagicMock()
        role.to_dict.return_value = {"role_name": "admin"}
        user.roles = [role]
        user.LAST_LOGIN_AT = None
        mock_rbac.get_users.return_value = ([user], 1)

        resp = client.post("/api/rbac/get_users", json={})
        assert resp.status_code == 200
        assert resp.json()["result"][0]["username"] == "test"
        assert resp.json()["result"][0]["pris"] == ["admin"]

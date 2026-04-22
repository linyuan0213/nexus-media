# -*- coding: utf-8 -*-
"""
RBAC 领域层测试
测试 RBAC 实体 from_orm/to_dict 以及适配器代理行为
"""
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from app.domain.entities.rbac import (
    RBACUserEntity,
    RBACRoleEntity,
    RBACPermissionEntity,
    RBACMenuEntity,
    RBACUserLoginLogEntity,
    RBACOperationLogEntity,
)
from app.db.repositories.rbac_repo_adapter import (
    RBACUserRepositoryAdapter,
    RBACRoleRepositoryAdapter,
    RBACPermissionRepositoryAdapter,
    RBACMenuRepositoryAdapter,
    RBACLogRepositoryAdapter,
)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _make_orm(**kwargs):
    """构造一个带大写属性的 mock ORM 对象"""
    m = MagicMock()
    for k, v in kwargs.items():
        setattr(m, k, v)
    return m


# ==================================================================
# Entity tests
# ==================================================================
class TestRBACUserEntity:
    def test_from_orm_full(self):
        now = datetime.now()
        orm = _make_orm(
            ID=1, USERNAME="admin", PASSWORD_HASH="h", EMAIL="a@b.com",
            NICKNAME="nick", AVATAR="ava", STATUS=1, IS_SUPERADMIN=1,
            LAST_LOGIN_AT=now, LAST_LOGIN_IP="127.0.0.1",
            CREATED_AT=now, UPDATED_AT=now,
        )
        e = RBACUserEntity.from_orm(orm)
        assert e.id == 1
        assert e.username == "admin"
        assert e.email == "a@b.com"
        assert e.is_superadmin == 1
        assert e.last_login_at == now

    def test_from_orm_none(self):
        assert RBACUserEntity.from_orm(None) is None

    def test_to_dict(self):
        now = datetime(2025, 1, 1, 12, 0, 0)
        e = RBACUserEntity(
            id=1, username="u", password_hash="h", email=None,
            nickname=None, avatar=None, status=1, is_superadmin=0,
            last_login_at=now, last_login_ip=None,
            created_at=now, updated_at=None,
        )
        d = e.to_dict()
        assert d["username"] == "u"
        assert d["last_login_at"] == "2025-01-01 12:00:00"
        assert d["created_at"] == "2025-01-01 12:00:00"
        assert d["last_login_ip"] is None

    def test_getattr_uppercase_compat(self):
        e = RBACUserEntity(
            id=1, username="u", password_hash="h", email=None,
            nickname=None, avatar=None, status=1, is_superadmin=0,
            last_login_at=None, last_login_ip=None,
            created_at=None, updated_at=None,
        )
        # 大写属性名兼容
        assert e.USERNAME == "u"
        assert e.ID == 1
        with pytest.raises(AttributeError):
            _ = e.NOT_EXIST


class TestRBACRoleEntity:
    def test_from_orm(self):
        orm = _make_orm(
            ID=2, ROLE_NAME="admin", ROLE_CODE="admin",
            DESCRIPTION="desc", ROLE_LEVEL=10, STATUS=1,
            CREATED_AT=None, UPDATED_AT=None,
        )
        e = RBACRoleEntity.from_orm(orm)
        assert e.role_name == "admin"
        assert e.role_level == 10

    def test_to_dict(self):
        e = RBACRoleEntity(
            id=2, role_name="r", role_code="rc",
            description=None, role_level=100, status=1,
            created_at=None, updated_at=None,
        )
        assert e.to_dict()["role_code"] == "rc"


class TestRBACPermissionEntity:
    def test_from_orm(self):
        orm = _make_orm(
            ID=3, PERMISSION_NAME="p", PERMISSION_CODE="pc",
            DESCRIPTION=None, PERMISSION_TYPE="api", MODULE="sys",
            STATUS=1, CREATED_AT=None, UPDATED_AT=None,
        )
        e = RBACPermissionEntity.from_orm(orm)
        assert e.permission_code == "pc"
        assert e.module == "sys"

    def test_to_dict(self):
        e = RBACPermissionEntity(
            id=3, permission_name="p", permission_code="pc",
            description=None, permission_type="api", module="sys",
            status=1, created_at=None, updated_at=None,
        )
        assert e.to_dict()["module"] == "sys"


class TestRBACMenuEntity:
    def test_from_orm(self):
        orm = _make_orm(
            ID=4, MENU_NAME="m", MENU_CODE="mc", PARENT_ID=0,
            PATH="/p", ICON="i", COMPONENT="c", SORT_ORDER=1,
            MENU_LEVEL=1, IS_HIDDEN=0, IS_EXTERNAL=0,
            EXTERNAL_LINK=None, STATUS=1, PERMISSION_CODE=None,
            CREATED_AT=None, UPDATED_AT=None,
        )
        e = RBACMenuEntity.from_orm(orm)
        assert e.menu_code == "mc"
        assert e.is_hidden == 0

    def test_to_dict(self):
        e = RBACMenuEntity(
            id=4, menu_name="m", menu_code="mc", parent_id=None,
            path=None, icon=None, component=None, sort_order=0,
            menu_level=1, is_hidden=0, is_external=0,
            external_link=None, status=1, permission_code=None,
            created_at=None, updated_at=None,
        )
        assert e.to_dict()["menu_name"] == "m"


class TestRBACUserLoginLogEntity:
    def test_from_orm(self):
        orm = _make_orm(
            ID=5, USER_ID=1, USERNAME="u", LOGIN_IP="127.0.0.1",
            LOGIN_LOCATION=None, USER_AGENT=None, LOGIN_TYPE="password",
            LOGIN_STATUS=1, FAIL_REASON=None, LOGIN_AT=None,
        )
        e = RBACUserLoginLogEntity.from_orm(orm)
        assert e.username == "u"
        assert e.login_type == "password"


class TestRBACOperationLogEntity:
    def test_from_orm(self):
        orm = _make_orm(
            ID=6, USER_ID=1, USERNAME="u", MODULE="sys",
            OPERATION_TYPE="QUERY", DESCRIPTION=None,
            REQUEST_METHOD="GET", REQUEST_URL="/api", REQUEST_PARAMS=None,
            RESPONSE_DATA=None, OPERATION_IP="127.0.0.1",
            EXECUTION_TIME=100, OPERATION_STATUS=1,
            ERROR_MSG=None, OPERATED_AT=None,
        )
        e = RBACOperationLogEntity.from_orm(orm)
        assert e.operation_type == "QUERY"
        assert e.execution_time == 100


# ==================================================================
# Adapter tests
# ==================================================================
class TestRBACUserRepositoryAdapter:
    def _make(self):
        mock = MagicMock()
        mock.get_user_by_id = MagicMock(return_value=_make_orm(
            ID=1, USERNAME="u", PASSWORD_HASH="h", EMAIL=None,
            NICKNAME=None, AVATAR=None, STATUS=1, IS_SUPERADMIN=0,
            LAST_LOGIN_AT=None, LAST_LOGIN_IP=None,
            CREATED_AT=None, UPDATED_AT=None,
        ))
        mock.get_users = MagicMock(return_value=([], 0))
        mock.get_all_users = MagicMock(return_value=[])
        mock.is_user_exists = MagicMock(return_value=True)
        mock.is_email_exists = MagicMock(return_value=False)
        mock.create_user = MagicMock(return_value=mock.get_user_by_id.return_value)
        mock.update_user = MagicMock(return_value=True)
        mock.update_last_login = MagicMock(return_value=True)
        mock.delete_user = MagicMock(return_value=True)
        mock.hard_delete_user = MagicMock(return_value=True)
        mock.get_user_roles = MagicMock(return_value=[])
        mock.assign_roles_to_user = MagicMock(return_value=True)
        mock.add_role_to_user = MagicMock(return_value=True)
        mock.remove_role_from_user = MagicMock(return_value=True)
        return mock

    def test_get_user_by_id(self):
        mock = self._make()
        adapter = RBACUserRepositoryAdapter(repo=mock)
        result = adapter.get_user_by_id(1)
        assert result is not None
        assert result.username == "u"
        mock.get_user_by_id.assert_called_once_with(1)

    def test_get_users(self):
        mock = self._make()
        adapter = RBACUserRepositoryAdapter(repo=mock)
        rows, total = adapter.get_users(page=1, page_size=10)
        assert rows == []
        assert total == 0
        mock.get_users.assert_called_once_with(page=1, page_size=10, status=None)

    def test_is_user_exists(self):
        mock = self._make()
        adapter = RBACUserRepositoryAdapter(repo=mock)
        assert adapter.is_user_exists("admin") is True
        mock.is_user_exists.assert_called_once_with("admin")

    def test_create_user(self):
        mock = self._make()
        adapter = RBACUserRepositoryAdapter(repo=mock)
        result = adapter.create_user("u", "h", email="e")
        assert result.username == "u"
        mock.create_user.assert_called_once_with("u", "h", "e", None, 0)

    def test_update_and_delete(self):
        mock = self._make()
        adapter = RBACUserRepositoryAdapter(repo=mock)
        assert adapter.update_user(1, status=0) is True
        assert adapter.delete_user(1) is True
        assert adapter.hard_delete_user(1) is True

    def test_assign_roles(self):
        mock = self._make()
        adapter = RBACUserRepositoryAdapter(repo=mock)
        assert adapter.assign_roles_to_user(1, [1, 2]) is True
        mock.assign_roles_to_user.assert_called_once_with(1, [1, 2])

    def test_default_repo(self):
        adapter = RBACUserRepositoryAdapter()
        assert adapter._repo is not None


class TestRBACRoleRepositoryAdapter:
    def _make(self):
        mock = MagicMock()
        mock.get_role_by_id = MagicMock(return_value=_make_orm(
            ID=1, ROLE_NAME="r", ROLE_CODE="rc", DESCRIPTION=None,
            ROLE_LEVEL=100, STATUS=1, CREATED_AT=None, UPDATED_AT=None,
        ))
        mock.get_all_roles = MagicMock(return_value=[])
        mock.get_roles_page = MagicMock(return_value=([], 0))
        mock.is_role_exists = MagicMock(return_value=False)
        mock.create_role = MagicMock(return_value=mock.get_role_by_id.return_value)
        mock.update_role = MagicMock(return_value=True)
        mock.delete_role = MagicMock(return_value=True)
        mock.get_role_permissions = MagicMock(return_value=[])
        mock.assign_permissions_to_role = MagicMock(return_value=True)
        mock.get_role_menus = MagicMock(return_value=[])
        mock.assign_menus_to_role = MagicMock(return_value=True)
        return mock

    def test_get_role_by_id(self):
        mock = self._make()
        adapter = RBACRoleRepositoryAdapter(repo=mock)
        result = adapter.get_role_by_id(1)
        assert result.role_name == "r"
        mock.get_role_by_id.assert_called_once_with(1)

    def test_get_all_roles(self):
        mock = self._make()
        adapter = RBACRoleRepositoryAdapter(repo=mock)
        assert adapter.get_all_roles(status=1) == []
        mock.get_all_roles.assert_called_once_with(status=1)

    def test_create_role(self):
        mock = self._make()
        adapter = RBACRoleRepositoryAdapter(repo=mock)
        result = adapter.create_role("name", "code")
        assert result.role_code == "rc"

    def test_assign_permissions(self):
        mock = self._make()
        adapter = RBACRoleRepositoryAdapter(repo=mock)
        assert adapter.assign_permissions_to_role(1, [2, 3]) is True

    def test_default_repo(self):
        adapter = RBACRoleRepositoryAdapter()
        assert adapter._repo is not None


class TestRBACPermissionRepositoryAdapter:
    def _make(self):
        perm_orm = _make_orm(
            ID=1, PERMISSION_NAME="p", PERMISSION_CODE="pc",
            DESCRIPTION=None, PERMISSION_TYPE="api", MODULE="sys",
            STATUS=1, CREATED_AT=None, UPDATED_AT=None,
        )
        mock = MagicMock()
        mock.get_permission_by_id = MagicMock(return_value=perm_orm)
        mock.get_permission_by_code = MagicMock(return_value=perm_orm)
        mock.get_all_permissions = MagicMock(return_value=[])
        mock.get_permissions_by_codes = MagicMock(return_value=[])
        mock.create_permission = MagicMock(return_value=perm_orm)
        mock.update_permission = MagicMock(return_value=True)
        mock.delete_permission = MagicMock(return_value=True)
        return mock

    def test_get_permission_by_code(self):
        mock = self._make()
        adapter = RBACPermissionRepositoryAdapter(repo=mock)
        result = adapter.get_permission_by_code("pc")
        assert result.permission_code == "pc"
        mock.get_permission_by_code.assert_called_once_with("pc")

    def test_get_all_permissions(self):
        mock = self._make()
        adapter = RBACPermissionRepositoryAdapter(repo=mock)
        assert adapter.get_all_permissions(module="sys") == []
        mock.get_all_permissions.assert_called_once_with(module="sys", permission_type=None)

    def test_default_repo(self):
        adapter = RBACPermissionRepositoryAdapter()
        assert adapter._repo is not None


class TestRBACMenuRepositoryAdapter:
    def _make(self):
        mock = MagicMock()
        mock.get_menu_by_id = MagicMock(return_value=_make_orm(
            ID=1, MENU_NAME="m", MENU_CODE="mc", PARENT_ID=None,
            PATH="/p", ICON=None, COMPONENT=None, SORT_ORDER=0,
            MENU_LEVEL=1, IS_HIDDEN=0, IS_EXTERNAL=0,
            EXTERNAL_LINK=None, STATUS=1, PERMISSION_CODE=None,
            CREATED_AT=None, UPDATED_AT=None,
        ))
        mock.get_all_menus = MagicMock(return_value=[])
        mock.get_top_menus = MagicMock(return_value=[])
        mock.get_children_menus = MagicMock(return_value=[])
        mock.get_menu_tree = MagicMock(return_value=[])
        mock.get_user_menus = MagicMock(return_value=[])
        mock.create_menu = MagicMock(return_value=mock.get_menu_by_id.return_value)
        mock.update_menu = MagicMock(return_value=True)
        mock.delete_menu = MagicMock(return_value=True)
        return mock

    def test_get_menu_by_id(self):
        mock = self._make()
        adapter = RBACMenuRepositoryAdapter(repo=mock)
        result = adapter.get_menu_by_id(1)
        assert result.menu_name == "m"
        mock.get_menu_by_id.assert_called_once_with(1)

    def test_get_menu_tree(self):
        mock = self._make()
        adapter = RBACMenuRepositoryAdapter(repo=mock)
        assert adapter.get_menu_tree(include_hidden=True) == []
        mock.get_menu_tree.assert_called_once_with(include_hidden=True)

    def test_get_user_menus(self):
        mock = self._make()
        adapter = RBACMenuRepositoryAdapter(repo=mock)
        assert adapter.get_user_menus(1) == []
        mock.get_user_menus.assert_called_once_with(1)

    def test_default_repo(self):
        adapter = RBACMenuRepositoryAdapter()
        assert adapter._repo is not None


class TestRBACLogRepositoryAdapter:
    def _make(self):
        mock = MagicMock()
        mock.add_login_log = MagicMock(return_value=_make_orm(
            ID=1, USER_ID=1, USERNAME="u", LOGIN_IP=None,
            LOGIN_LOCATION=None, USER_AGENT=None, LOGIN_TYPE="password",
            LOGIN_STATUS=1, FAIL_REASON=None, LOGIN_AT=None,
        ))
        mock.get_login_logs = MagicMock(return_value=([], 0))
        mock.add_operation_log = MagicMock(return_value=_make_orm(
            ID=2, USER_ID=1, USERNAME="u", MODULE="sys",
            OPERATION_TYPE="QUERY", DESCRIPTION=None,
            REQUEST_METHOD="GET", REQUEST_URL="/api", REQUEST_PARAMS=None,
            RESPONSE_DATA=None, OPERATION_IP=None,
            EXECUTION_TIME=None, OPERATION_STATUS=1,
            ERROR_MSG=None, OPERATED_AT=None,
        ))
        mock.get_operation_logs = MagicMock(return_value=([], 0))
        return mock

    def test_add_login_log(self):
        mock = self._make()
        adapter = RBACLogRepositoryAdapter(repo=mock)
        result = adapter.add_login_log(1, "u", login_ip="127.0.0.1")
        assert result.username == "u"
        mock.add_login_log.assert_called_once_with(
            1, "u", "127.0.0.1", None, None, "password", 1, None,
        )

    def test_get_login_logs(self):
        mock = self._make()
        adapter = RBACLogRepositoryAdapter(repo=mock)
        rows, total = adapter.get_login_logs(user_id=1)
        assert rows == []
        assert total == 0

    def test_add_operation_log(self):
        mock = self._make()
        adapter = RBACLogRepositoryAdapter(repo=mock)
        result = adapter.add_operation_log(user_id=1, username="u", module="sys")
        assert result.operation_type == "QUERY"

    def test_default_repo(self):
        adapter = RBACLogRepositoryAdapter()
        assert adapter._repo is not None

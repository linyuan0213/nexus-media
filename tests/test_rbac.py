"""
RBAC (Role-Based Access Control) 模块测试
测试用户管理、角色管理、权限管理、菜单管理功能
"""
import pytest
from app.utils.security import generate_password_hash

# 测试数据库配置
from app.db import init_db, MainDb
from app.db.models.rbac import (
    RBACUser, RBACRole, RBACPermission, RBACMenu,
    RBACUserLoginLog, RBACOperationLog
)
from app.db.repositories import (
    RBACUserRepository,
    RBACRoleRepository,
    RBACPermissionRepository,
    RBACMenuRepository,
    RBACLogRepository
)
from app.services.rbac_service import rbac_service


@pytest.fixture(scope="module")
def db():
    """初始化测试数据库"""
    init_db()
    yield MainDb()
    # 清理测试数据


@pytest.fixture
def user_repo():
    """用户仓储实例"""
    return RBACUserRepository()


@pytest.fixture
def role_repo():
    """角色仓储实例"""
    return RBACRoleRepository()


@pytest.fixture
def permission_repo():
    """权限仓储实例"""
    return RBACPermissionRepository()


@pytest.fixture
def menu_repo():
    """菜单仓储实例"""
    return RBACMenuRepository()


@pytest.fixture
def log_repo():
    """日志仓储实例"""
    return RBACLogRepository()


class TestRBACUserRepository:
    """用户仓储测试"""
    
    def test_create_user(self, user_repo):
        """测试创建用户"""
        password_hash = generate_password_hash("test123")
        user = user_repo.create_user(
            username="testuser",
            password_hash=password_hash,
            email="test@example.com",
            nickname="Test User"
        )
        
        assert user is not None
        assert user.USERNAME == "testuser"
        assert user.EMAIL == "test@example.com"
        assert user.STATUS == 1
        
        # 清理
        user_repo.hard_delete_user(user.ID)
    
    def test_get_user_by_username(self, user_repo):
        """测试根据用户名获取用户"""
        password_hash = generate_password_hash("test123")
        user = user_repo.create_user(
            username="testuser2",
            password_hash=password_hash,
            email="test2@example.com"
        )
        
        found = user_repo.get_user_by_username("testuser2")
        assert found is not None
        assert found.USERNAME == "testuser2"
        
        # 清理
        user_repo.hard_delete_user(user.ID)
    
    def test_is_user_exists(self, user_repo):
        """测试检查用户是否存在"""
        password_hash = generate_password_hash("test123")
        user = user_repo.create_user(
            username="testuser3",
            password_hash=password_hash
        )
        
        assert user_repo.is_user_exists("testuser3") is True
        assert user_repo.is_user_exists("nonexistent") is False
        
        # 清理
        user_repo.hard_delete_user(user.ID)
    
    def test_update_user(self, user_repo):
        """测试更新用户信息"""
        password_hash = generate_password_hash("test123")
        user = user_repo.create_user(
            username="testuser4",
            password_hash=password_hash
        )
        
        success = user_repo.update_user(user.ID, NICKNAME="Updated Nickname")
        assert success is True
        
        updated = user_repo.get_user_by_id(user.ID)
        assert updated.NICKNAME == "Updated Nickname"
        
        # 清理
        user_repo.hard_delete_user(user.ID)
    
    def test_delete_user(self, user_repo):
        """测试删除用户（软删除）"""
        password_hash = generate_password_hash("test123")
        user = user_repo.create_user(
            username="testuser5",
            password_hash=password_hash
        )
        
        success = user_repo.delete_user(user.ID)
        assert success is True
        
        deleted = user_repo.get_user_by_id(user.ID)
        assert deleted.STATUS == 0
        
        # 清理
        user_repo.hard_delete_user(user.ID)
    
    def test_assign_roles_to_user(self, user_repo, role_repo):
        """测试为用户分配角色"""
        # 创建测试角色
        role = role_repo.create_role(
            role_name="Test Role",
            role_code="test_role"
        )
        
        # 创建测试用户
        password_hash = generate_password_hash("test123")
        user = user_repo.create_user(
            username="testuser6",
            password_hash=password_hash
        )
        
        # 分配角色
        success = user_repo.assign_roles_to_user(user.ID, [role.ID])
        assert success is True
        
        # 验证
        user_roles = user_repo.get_user_roles(user.ID)
        assert len(user_roles) == 1
        assert user_roles[0].ROLE_CODE == "test_role"
        
        # 清理
        user_repo.hard_delete_user(user.ID)
        role_repo.delete_role(role.ID)


class TestRBACRoleRepository:
    """角色仓储测试"""
    
    def test_create_role(self, role_repo):
        """测试创建角色"""
        role = role_repo.create_role(
            role_name="Admin",
            role_code="admin",
            description="Administrator role",
            role_level=10
        )
        
        assert role is not None
        assert role.ROLE_NAME == "Admin"
        assert role.ROLE_CODE == "admin"
        assert role.ROLE_LEVEL == 10
        
        # 清理
        role_repo.delete_role(role.ID)
    
    def test_get_role_by_code(self, role_repo):
        """测试根据角色代码获取角色"""
        role = role_repo.create_role(
            role_name="User",
            role_code="user"
        )
        
        found = role_repo.get_role_by_code("user")
        assert found is not None
        assert found.ROLE_NAME == "User"
        
        # 清理
        role_repo.delete_role(role.ID)
    
    def test_is_role_exists(self, role_repo):
        """测试检查角色是否存在"""
        role = role_repo.create_role(
            role_name="Manager",
            role_code="manager"
        )
        
        assert role_repo.is_role_exists("manager") is True
        assert role_repo.is_role_exists("nonexistent") is False
        
        # 清理
        role_repo.delete_role(role.ID)
    
    def test_assign_permissions_to_role(self, role_repo, permission_repo):
        """测试为角色分配权限"""
        # 创建测试权限
        perm = permission_repo.create_permission(
            permission_name="View Users",
            permission_code="user:view",
            permission_type="api"
        )
        
        # 创建测试角色
        role = role_repo.create_role(
            role_name="Test Role",
            role_code="test_role_perm"
        )
        
        # 分配权限
        success = role_repo.assign_permissions_to_role(role.ID, [perm.ID])
        assert success is True
        
        # 验证
        role_perms = role_repo.get_role_permissions(role.ID)
        assert len(role_perms) == 1
        assert role_perms[0].PERMISSION_CODE == "user:view"
        
        # 清理
        role_repo.delete_role(role.ID)
        permission_repo.delete_permission(perm.ID)
    
    def test_assign_menus_to_role(self, role_repo, menu_repo):
        """测试为角色分配菜单"""
        # 创建测试菜单
        menu = menu_repo.create_menu(
            menu_name="User Management",
            menu_code="user_mgmt",
            path="/users"
        )
        
        # 创建测试角色
        role = role_repo.create_role(
            role_name="Test Role",
            role_code="test_role_menu"
        )
        
        # 分配菜单
        success = role_repo.assign_menus_to_role(role.ID, [menu.ID])
        assert success is True
        
        # 验证
        role_menus = role_repo.get_role_menus(role.ID)
        assert len(role_menus) == 1
        assert role_menus[0].MENU_CODE == "user_mgmt"
        
        # 清理
        role_repo.delete_role(role.ID)
        menu_repo.delete_menu(menu.ID)


class TestRBACPermissionRepository:
    """权限仓储测试"""
    
    def test_create_permission(self, permission_repo):
        """测试创建权限"""
        perm = permission_repo.create_permission(
            permission_name="Create User",
            permission_code="user:create",
            permission_type="api",
            module="user"
        )
        
        assert perm is not None
        assert perm.PERMISSION_NAME == "Create User"
        assert perm.PERMISSION_CODE == "user:create"
        assert perm.PERMISSION_TYPE == "api"
        
        # 清理
        permission_repo.delete_permission(perm.ID)
    
    def test_get_permission_by_code(self, permission_repo):
        """测试根据权限代码获取权限"""
        perm = permission_repo.create_permission(
            permission_name="Delete User",
            permission_code="user:delete"
        )
        
        found = permission_repo.get_permission_by_code("user:delete")
        assert found is not None
        assert found.PERMISSION_NAME == "Delete User"
        
        # 清理
        permission_repo.delete_permission(perm.ID)
    
    def test_get_all_permissions(self, permission_repo):
        """测试获取所有权限"""
        perm1 = permission_repo.create_permission(
            permission_name="Perm 1",
            permission_code="perm:1",
            module="test"
        )
        perm2 = permission_repo.create_permission(
            permission_name="Perm 2",
            permission_code="perm:2",
            module="test"
        )
        
        perms = permission_repo.get_all_permissions(module="test")
        assert len(perms) >= 2
        
        # 清理
        permission_repo.delete_permission(perm1.ID)
        permission_repo.delete_permission(perm2.ID)


class TestRBACMenuRepository:
    """菜单仓储测试"""
    
    def test_create_menu(self, menu_repo):
        """测试创建菜单"""
        menu = menu_repo.create_menu(
            menu_name="Dashboard",
            menu_code="dashboard",
            path="/dashboard",
            icon="home",
            sort_order=1,
            menu_level=1
        )
        
        assert menu is not None
        assert menu.MENU_NAME == "Dashboard"
        assert menu.PATH == "/dashboard"
        
        # 清理
        menu_repo.delete_menu(menu.ID)
    
    def test_create_submenu(self, menu_repo):
        """测试创建子菜单"""
        # 创建父菜单
        parent = menu_repo.create_menu(
            menu_name="Settings",
            menu_code="settings"
        )
        
        # 创建子菜单
        child = menu_repo.create_menu(
            menu_name="User Settings",
            menu_code="user_settings",
            parent_id=parent.ID,
            path="/settings/user",
            menu_level=2
        )
        
        assert child.PARENT_ID == parent.ID
        assert child.MENU_LEVEL == 2
        
        # 清理
        menu_repo.delete_menu(child.ID)
        menu_repo.delete_menu(parent.ID)
    
    def test_get_menu_tree(self, menu_repo):
        """测试获取菜单树"""
        # 创建菜单结构
        parent = menu_repo.create_menu(
            menu_name="System",
            menu_code="system"
        )
        child = menu_repo.create_menu(
            menu_name="Logs",
            menu_code="logs",
            parent_id=parent.ID
        )
        
        tree = menu_repo.get_menu_tree()
        assert len(tree) > 0
        
        # 清理
        menu_repo.delete_menu(child.ID)
        menu_repo.delete_menu(parent.ID)


class TestRBACService:
    """RBAC服务测试"""
    
    def test_authenticate_user_success(self):
        """测试用户认证成功"""
        # 创建测试用户
        success, result = rbac_service.create_user(
            username="authtest",
            password="password123",
            email="authtest@example.com"
        )
        assert success is True
        user = result
        
        # 认证
        success, result = rbac_service.authenticate_user("authtest", "password123")
        assert success is True
        assert result.USERNAME == "authtest"
        
        # 清理
        rbac_service.delete_user(user.ID)
    
    def test_authenticate_user_failure(self):
        """测试用户认证失败"""
        success, result = rbac_service.authenticate_user("nonexistent", "wrongpass")
        assert success is False
        assert "错误" in result or "不存在" in result
    
    def test_check_permission(self):
        """测试权限检查"""
        # 创建用户、角色和权限
        success, user = rbac_service.create_user(
            username="permtest",
            password="password123"
        )
        assert success is True
        
        success, role = rbac_service.create_role(
            role_name="Perm Test Role",
            role_code="perm_test_role"
        )
        assert success is True
        
        # 创建权限
        success, perm = rbac_service.create_permission(
            permission_name="Test Permission",
            permission_code="test:permission"
        )
        assert success is True
        
        # 分配权限给角色
        rbac_service.assign_permissions_to_role(role.ID, [perm.ID])
        
        # 分配角色给用户
        rbac_service.assign_roles_to_user(user.ID, [role.ID])
        
        # 检查权限
        has_perm = rbac_service.check_permission(user.ID, "test:permission")
        assert has_perm is True
        
        has_perm = rbac_service.check_permission(user.ID, "nonexistent:permission")
        assert has_perm is False
        
        # 清理
        rbac_service.delete_user(user.ID)
        rbac_service.delete_role(role.ID)
        rbac_service.delete_permission(perm.ID)
    
    def test_check_permission_superadmin(self):
        """测试超级管理员拥有所有权限"""
        # 创建超级管理员
        success, user = rbac_service.create_user(
            username="superadmintest",
            password="password123",
            is_superadmin=1
        )
        assert success is True
        
        # 超级管理员应该拥有所有权限
        has_perm = rbac_service.check_permission(user.ID, "any:permission")
        assert has_perm is True
        
        # 清理
        rbac_service.delete_user(user.ID)
    
    def test_get_user_permissions(self):
        """测试获取用户所有权限"""
        # 创建用户和多个权限
        success, user = rbac_service.create_user(
            username="permuser",
            password="password123"
        )
        assert success is True
        
        success, role = rbac_service.create_role(
            role_name="Multi Perm Role",
            role_code="multi_perm_role"
        )
        assert success is True
        
        # 创建多个权限
        success, perm1 = rbac_service.create_permission(
            permission_name="Perm 1",
            permission_code="test:perm1"
        )
        success, perm2 = rbac_service.create_permission(
            permission_name="Perm 2",
            permission_code="test:perm2"
        )
        
        # 分配权限
        rbac_service.assign_permissions_to_role(role.ID, [perm1.ID, perm2.ID])
        rbac_service.assign_roles_to_user(user.ID, [role.ID])
        
        # 获取权限
        perms = rbac_service.get_user_permissions(user.ID)
        assert "test:perm1" in perms
        assert "test:perm2" in perms
        
        # 清理
        rbac_service.delete_user(user.ID)
        rbac_service.delete_role(role.ID)
        rbac_service.delete_permission(perm1.ID)
        rbac_service.delete_permission(perm2.ID)


class TestRBACServiceMenu:
    """RBAC菜单服务测试"""
    
    def test_create_menu(self):
        """测试创建菜单"""
        success, result = rbac_service.create_menu(
            menu_name="Test Menu",
            menu_code="test_menu",
            path="/test"
        )
        assert success is True
        
        menu = result
        assert menu.MENU_NAME == "Test Menu"
        
        # 清理
        rbac_service.delete_menu(menu.ID)
    
    def test_get_menu_tree(self):
        """测试获取菜单树"""
        # 创建菜单结构
        success, parent = rbac_service.create_menu(
            menu_name="Parent",
            menu_code="parent_menu"
        )
        assert success is True
        
        success, child = rbac_service.create_menu(
            menu_name="Child",
            menu_code="child_menu",
            parent_id=parent.ID
        )
        assert success is True
        
        # 获取树
        tree = rbac_service.get_menu_tree()
        assert isinstance(tree, list)
        assert len(tree) > 0
        
        # 清理
        rbac_service.delete_menu(child.ID)
        rbac_service.delete_menu(parent.ID)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

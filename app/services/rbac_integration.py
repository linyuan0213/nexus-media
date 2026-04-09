"""
RBAC集成模块 - 用于服务器端模板渲染架构
提供与现有系统的无缝集成
"""
from functools import wraps
from typing import List, Optional, Dict, Any, Set

from flask import g, session, request, abort
from flask_login import current_user

from app.services.rbac_service import rbac_service
from app.db.repositories import RBACMenuRepository, RBACUserRepository
import log


class RBACContext:
    """
    RBAC上下文管理器
    用于在请求上下文中缓存用户的权限信息
    """
    
    @staticmethod
    def get_current_user_id() -> Optional[int]:
        """获取当前用户ID"""
        if current_user.is_authenticated:
            return current_user.get_id()
        return None
    
    @staticmethod
    def is_superadmin() -> bool:
        """检查当前用户是否为超级管理员"""
        user_id = RBACContext.get_current_user_id()
        if not user_id:
            return False
        
        user = rbac_service.get_user_by_id(user_id)
        if user and user.IS_SUPERADMIN == 1:
            return True
        return False
    
    @staticmethod
    def get_user_permissions() -> Set[str]:
        """获取当前用户的所有权限代码"""
        user_id = RBACContext.get_current_user_id()
        if not user_id:
            return set()
        
        # 使用Flask g对象缓存
        if hasattr(g, 'rbac_permissions'):
            return g.rbac_permissions
        
        permissions = rbac_service.get_user_permissions(user_id)
        g.rbac_permissions = permissions
        return permissions
    
    @staticmethod
    def get_user_menus() -> List[Dict[str, Any]]:
        """获取当前用户可访问的菜单列表"""
        user_id = RBACContext.get_current_user_id()
        if not user_id:
            return []
        
        # 使用Flask g对象缓存
        if hasattr(g, 'rbac_menus'):
            return g.rbac_menus
        
        menus = rbac_service.get_user_menus(user_id)
        menu_list = [menu.to_dict() for menu in menus]
        g.rbac_menus = menu_list
        return menu_list
    
    @staticmethod
    def has_permission(permission_code: str) -> bool:
        """检查当前用户是否有指定权限"""
        if RBACContext.is_superadmin():
            return True
        
        permissions = RBACContext.get_user_permissions()
        return permission_code in permissions
    
    @staticmethod
    def has_any_permission(permission_codes: List[str]) -> bool:
        """检查当前用户是否有任一指定权限"""
        if RBACContext.is_superadmin():
            return True
        
        permissions = RBACContext.get_user_permissions()
        return any(code in permissions for code in permission_codes)
    
    @staticmethod
    def has_all_permissions(permission_codes: List[str]) -> bool:
        """检查当前用户是否有所有指定权限"""
        if RBACContext.is_superadmin():
            return True
        
        permissions = RBACContext.get_user_permissions()
        return all(code in permissions for code in permission_codes)
    
    @staticmethod
    def can_access_menu(menu_code: str) -> bool:
        """检查当前用户是否可以访问指定菜单"""
        if RBACContext.is_superadmin():
            return True
        
        user_id = RBACContext.get_current_user_id()
        if not user_id:
            return False
        
        return rbac_service.check_menu_access(user_id, menu_code)
    
    @staticmethod
    def get_menu_tree_for_user() -> List[Dict[str, Any]]:
        """
        获取当前用户的菜单树（过滤掉无权限访问的菜单）
        """
        user_id = RBACContext.get_current_user_id()
        if not user_id:
            return []
        
        # 超级管理员返回完整菜单树
        if RBACContext.is_superadmin():
            return rbac_service.get_menu_tree()
        
        # 普通用户返回有权限的菜单
        menus = rbac_service.get_user_menus(user_id)
        
        # 构建菜单树
        menu_dict = {}
        for menu in menus:
            menu_dict[menu.ID] = menu.to_dict()
        
        # 构建树形结构
        tree = []
        for menu in menus:
            menu_data = menu_dict[menu.ID]
            if menu.PARENT_ID is None:
                tree.append(menu_data)
            else:
                # 找到父菜单并添加为子菜单
                parent = menu_dict.get(menu.PARENT_ID)
                if parent:
                    if 'children' not in parent:
                        parent['children'] = []
                    parent['children'].append(menu_data)
        
        return tree


def require_permission(permission_code: str):
    """
    权限检查装饰器（用于视图函数）
    
    用法:
        @app.route('/admin/users')
        @login_required
        @require_permission('user:view')
        def admin_users():
            return render_template('users.html')
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not RBACContext.has_permission(permission_code):
                abort(403, description="无权访问此页面")
            return func(*args, **kwargs)
        return wrapper
    return decorator


def require_any_permission(permission_codes: List[str]):
    """
    任一权限检查装饰器
    
    用法:
        @app.route('/admin/content')
        @login_required
        @require_any_permission(['post:create', 'page:create'])
        def admin_content():
            return render_template('content.html')
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not RBACContext.has_any_permission(permission_codes):
                abort(403, description="无权访问此页面")
            return func(*args, **kwargs)
        return wrapper
    return decorator


def require_all_permissions(permission_codes: List[str]):
    """
    所有权限检查装饰器
    
    用法:
        @app.route('/admin/sensitive')
        @login_required
        @require_all_permissions(['user:delete', 'user:view'])
        def admin_sensitive():
            return render_template('sensitive.html')
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not RBACContext.has_all_permissions(permission_codes):
                abort(403, description="无权访问此页面")
            return func(*args, **kwargs)
        return wrapper
    return decorator


def menu_permission_required(menu_code: str):
    """
    菜单访问权限装饰器
    
    用法:
        @app.route('/settings')
        @login_required
        @menu_permission_required('setting')
        def settings():
            return render_template('settings.html')
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not RBACContext.can_access_menu(menu_code):
                abort(403, description="无权访问此菜单")
            return func(*args, **kwargs)
        return wrapper
    return decorator


# ========== 模板上下文处理器 ==========

def rbac_context_processor():
    """
    RBAC模板上下文处理器
    向所有模板注入RBAC相关变量和函数
    
    在Flask应用中注册:
        app.context_processor(rbac_context_processor)
    """
    return {
        # 权限检查函数
        'has_permission': RBACContext.has_permission,
        'has_any_permission': RBACContext.has_any_permission,
        'has_all_permissions': RBACContext.has_all_permissions,
        
        # 菜单相关
        'can_access_menu': RBACContext.can_access_menu,
        'get_user_menus': RBACContext.get_menu_tree_for_user,
        
        # 用户信息
        'is_superadmin': RBACContext.is_superadmin(),
        'current_user_permissions': RBACContext.get_user_permissions(),
    }


# ========== 与旧系统兼容的User类包装器 ==========

class RBACUserWrapper:
    """
    RBAC用户包装器
    兼容旧的User类接口，同时支持RBAC功能
    """
    
    def __init__(self, rbac_user=None):
        self._rbac_user = rbac_user
    
    @property
    def id(self):
        return self._rbac_user.ID if self._rbac_user else None
    
    @property
    def username(self):
        return self._rbac_user.USERNAME if self._rbac_user else None
    
    @property
    def is_admin(self):
        """是否管理员（兼容旧接口）"""
        if not self._rbac_user:
            return False
        return self._rbac_user.IS_SUPERADMIN == 1 or RBACContext.has_permission('user:view')
    
    @property
    def level(self):
        """用户级别（兼容旧接口）"""
        if not self._rbac_user:
            return 0
        if self._rbac_user.IS_SUPERADMIN == 1:
            return 2
        if RBACContext.has_permission('setting:view'):
            return 2
        return 1
    
    def get_id(self):
        return self.id
    
    def verify_password(self, password: str) -> bool:
        """验证密码"""
        from werkzeug.security import check_password_hash
        if not self._rbac_user:
            return False
        return check_password_hash(self._rbac_user.PASSWORD_HASH, password)
    
    def get_pris(self) -> str:
        """
        获取权限字符串（兼容旧接口）
        返回逗号分隔的权限代码
        """
        if not self._rbac_user:
            return ""
        
        permissions = RBACContext.get_user_permissions()
        return ",".join(permissions)
    
    def get_topmenus(self) -> List[str]:
        """
        获取顶级菜单列表（兼容旧接口）
        """
        menus = RBACContext.get_menu_tree_for_user()
        return [m['menu_name'] for m in menus if m.get('menu_level') == 1]
    
    def get_usermenus(self, ignore: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        获取用户菜单（兼容旧接口）
        返回格式与旧系统兼容的菜单列表
        """
        menu_tree = RBACContext.get_menu_tree_for_user()
        
        # 转换为旧格式
        result = []
        for menu in menu_tree:
            if ignore and menu.get('menu_code') in ignore:
                continue
            
            menu_item = {
                'name': menu['menu_name'],
                'page': menu.get('path', ''),
                'icon': menu.get('icon', ''),
                'level': menu.get('menu_level', 1),
            }
            
            # 处理子菜单
            if menu.get('children'):
                menu_item['list'] = []
                for child in menu['children']:
                    if ignore and child.get('menu_code') in ignore:
                        continue
                    menu_item['list'].append({
                        'name': child['menu_name'],
                        'page': child.get('path', ''),
                        'icon': child.get('icon', ''),
                        'level': child.get('menu_level', 2),
                    })
            
            result.append(menu_item)
        
        return result
    
    @classmethod
    def get_by_username(cls, username: str) -> Optional['RBACUserWrapper']:
        """根据用户名获取用户包装器"""
        user = rbac_service.get_user_by_username(username)
        if user:
            return cls(user)
        return None
    
    @classmethod
    def get_by_id(cls, user_id: int) -> Optional['RBACUserWrapper']:
        """根据ID获取用户包装器"""
        user = rbac_service.get_user_by_id(user_id)
        if user:
            return cls(user)
        return None


# ========== 权限检查快捷函数 ==========

def check_page_permission(page_code: str) -> bool:
    """
    检查页面访问权限
    
    Args:
        page_code: 页面代码，如 'users', 'settings', 'site'
    
    Returns:
        是否有权限访问
    """
    permission_map = {
        'users': 'user:view',
        'roles': 'role:view',
        'permissions': 'permission:view',
        'menus': 'menu:view',
        'settings': 'setting:view',
        'site': 'site:view',
        'library': 'library:view',
        'download': 'download:view',
        'rss': 'rss:view',
        'search': 'search:view',
        'service': 'service:view',
        'plugin': 'plugin:view',
    }
    
    permission_code = permission_map.get(page_code)
    if permission_code:
        return RBACContext.has_permission(permission_code)
    
    # 默认允许访问
    return True


def get_sidebar_menus() -> List[Dict[str, Any]]:
    """
    获取侧边栏菜单
    用于模板渲染
    """
    return RBACContext.get_menu_tree_for_user()


# ========== 初始化函数 ==========

def init_rbac_for_app(app, admin_username: str = None, admin_password: str = None):
    """
    初始化RBAC系统集成到Flask应用
    
    Args:
        app: Flask应用实例
        admin_username: 管理员用户名（首次初始化）
        admin_password: 管理员密码（首次初始化）
    """
    from app.services.rbac_init import init_rbac_system, init_admin_user
    
    # 注册模板上下文处理器
    app.context_processor(rbac_context_processor)
    
    # 初始化RBAC系统数据
    init_rbac_system()
    
    # 创建管理员用户（如果指定）
    if admin_username and admin_password:
        init_admin_user(admin_username, admin_password)
    
    log.info("【RBAC】系统集成完成")

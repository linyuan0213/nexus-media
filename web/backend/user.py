"""
用户管理模块 - RBAC版本
基于角色的访问控制(RBAC)用户管理
"""
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash
from typing import List, Optional, Dict, Any

from app.services.rbac_service import rbac_service
from app.db.repositories import RBACUserRepository, RBACRoleRepository, RBACMenuRepository
from app.db.models.rbac import RBACUser
from app.conf import ModuleConf
import log


# 服务配置常量 - 使用Lucide图标
SERVICE_CONF = {
    'rssdownload': {
        'name': '电影/电视剧订阅',
        'icon': 'cloud-download',
        'color': 'blue',
        'level': 2
    },
    'subscribe_search_all': {
        'name': '订阅搜索',
        'icon': 'search',
        'color': 'blue',
        'level': 2
    },
    'pttransfer': {
        'name': '下载文件转移',
        'icon': 'replace',
        'color': 'green',
        'level': 2
    },
    'sync': {
        'name': '目录同步',
        'time': '实时监控',
        'icon': 'refresh-cw',
        'color': 'orange',
        'level': 1
    },
    'blacklist': {
        'name': '清理转移缓存',
        'time': '手动',
        'state': 'OFF',
        'icon': 'eraser',
        'color': 'red',
        'level': 1
    },
    'rsshistory': {
        'name': '清理RSS缓存',
        'time': '手动',
        'state': 'OFF',
        'icon': 'eraser',
        'color': 'purple',
        'level': 2
    },
    'nametest': {
        'name': '名称识别测试',
        'time': '',
        'state': 'OFF',
        'icon': 'type',
        'color': 'lime',
        'level': 1
    },
    'ruletest': {
        'name': '过滤规则测试',
        'time': '',
        'state': 'OFF',
        'icon': 'sliders-horizontal',
        'color': 'yellow',
        'level': 2
    },
    'nettest': {
        'name': '网络连通性测试',
        'time': '',
        'state': 'OFF',
        'icon': 'network',
        'color': 'cyan',
        'targets': ModuleConf.NETTEST_TARGETS if hasattr(ModuleConf, 'NETTEST_TARGETS') else [],
        'level': 1
    },
    'backup': {
        'name': '备份&恢复',
        'time': '',
        'state': 'OFF',
        'icon': 'database-backup',
        'color': 'green',
        'level': 1
    },
    'processes': {
        'name': '系统进程',
        'time': '',
        'state': 'OFF',
        'icon': 'terminal',
        'color': 'muted',
        'level': 1
    }
}


class User(UserMixin):
    """
    用户类 - 兼容Flask-Login
    封装RBAC用户模型，提供统一的用户管理接口
    """
    
    def __init__(self, user: Optional[RBACUser] = None):
        """
        初始化用户
        
        Args:
            user: RBAC用户模型实例
        """
        self._user = user
        self._permissions_cache = None
        self._menus_cache = None
    
    # ========== Flask-Login 必需方法 ==========
    
    def get_id(self) -> int:
        """获取用户ID（Flask-Login必需）"""
        return self._user.ID if self._user else None
    
    @property
    def is_authenticated(self) -> bool:
        """是否已认证"""
        return self._user is not None and self._user.STATUS == 1
    
    @property
    def is_active(self) -> bool:
        """是否激活"""
        return self._user is not None and self._user.STATUS == 1
    
    @property
    def is_anonymous(self) -> bool:
        """是否匿名用户"""
        return self._user is None
    
    # ========== 用户属性 ==========
    
    @property
    def id(self) -> int:
        """用户ID"""
        return self._user.ID if self._user else None
    
    @property
    def username(self) -> str:
        """用户名"""
        return self._user.USERNAME if self._user else None
    
    @property
    def nickname(self) -> str:
        """昵称"""
        return self._user.NICKNAME if self._user else self.username
    
    @property
    def email(self) -> str:
        """邮箱"""
        return self._user.EMAIL if self._user else None
    
    @property
    def avatar(self) -> str:
        """头像"""
        return self._user.AVATAR if self._user else None
    
    @property
    def is_admin(self) -> bool:
        """是否管理员"""
        if not self._user:
            return False
        # 超级管理员或拥有用户管理权限
        return (self._user.IS_SUPERADMIN == 1 or 
                rbac_service.check_permission(self._user.ID, 'user:view'))
    
    @property
    def is_superadmin(self) -> bool:
        """是否超级管理员"""
        return self._user is not None and self._user.IS_SUPERADMIN == 1
    
    @property
    def level(self) -> int:
        """
        用户级别（兼容旧接口）
        2 = 管理员, 1 = 普通用户
        """
        if self.is_superadmin:
            return 2
        if self.is_admin:
            return 2
        return 1
    
    @property
    def status(self) -> int:
        """用户状态: 1=启用, 0=禁用"""
        return self._user.STATUS if self._user else 0
    
    @property
    def last_login_at(self) -> str:
        """最后登录时间"""
        if self._user and self._user.LAST_LOGIN_AT:
            return self._user.LAST_LOGIN_AT.strftime('%Y-%m-%d %H:%M')
        return None
    
    # ========== 密码验证 ==========
    
    def verify_password(self, password: str) -> bool:
        """
        验证密码
        
        Args:
            password: 明文密码
            
        Returns:
            是否验证通过
        """
        if not self._user or not self._user.PASSWORD_HASH:
            return False
        return check_password_hash(self._user.PASSWORD_HASH, password)
    
    def update_last_login(self, login_ip: str = None) -> bool:
        """
        更新最后登录时间
        
        Args:
            login_ip: 登录IP
            
        Returns:
            是否更新成功
        """
        if not self._user:
            return False
        try:
            rbac_service.user_repo.update_last_login(self.id, login_ip)
            return True
        except Exception:
            return False
    
    # ========== 权限相关 ==========
    
    def get_permissions(self) -> List[str]:
        """
        获取用户的所有权限代码列表
        
        Returns:
            权限代码列表
        """
        if self._permissions_cache is None:
            # 通过 Service 层获取权限，超级管理员会自动返回所有权限
            perms = rbac_service.get_user_permissions(self.id)
            self._permissions_cache = list(perms)
        return self._permissions_cache
    
    def has_permission(self, permission_code: str) -> bool:
        """
        检查是否拥有指定权限
        
        Args:
            permission_code: 权限代码
            
        Returns:
            是否拥有权限
        """
        if self.is_superadmin:
            return True
        return rbac_service.check_permission(self.id, permission_code)
    
    def has_any_permission(self, permission_codes: List[str]) -> bool:
        """
        检查是否拥有任一指定权限
        
        Args:
            permission_codes: 权限代码列表
            
        Returns:
            是否拥有任一权限
        """
        if self.is_superadmin:
            return True
        return rbac_service.check_any_permission(self.id, permission_codes)
    
    def has_all_permissions(self, permission_codes: List[str]) -> bool:
        """
        检查是否拥有所有指定权限
        
        Args:
            permission_codes: 权限代码列表
            
        Returns:
            是否拥有所有权限
        """
        if self.is_superadmin:
            return True
        return rbac_service.check_all_permissions(self.id, permission_codes)
    
    def get_pris(self) -> str:
        """
        获取权限字符串（兼容旧接口）
        返回逗号分隔的权限代码
        """
        return ",".join(self.get_permissions())
    
    # ========== 菜单相关 ==========
    
    def get_menus(self) -> List[Dict[str, Any]]:
        """
        获取用户的菜单列表
        
        Returns:
            菜单字典列表
        """
        if self._menus_cache is None:
            menus = rbac_service.get_user_menus(self.id)
            self._menus_cache = [menu.to_dict() for menu in menus]
        return self._menus_cache
    
    def get_menu_tree(self) -> List[Dict[str, Any]]:
        """
        获取用户的菜单树形结构
        
        Returns:
            菜单树形结构
        """
        if self.is_superadmin:
            return rbac_service.get_menu_tree()
        
        # 构建菜单树
        menus = self.get_menus()
        menu_dict = {m['id']: m for m in menus}
        
        tree = []
        for menu in menus:
            if menu.get('parent_id') is None:
                tree.append(menu)
            else:
                parent = menu_dict.get(menu['parent_id'])
                if parent:
                    if 'children' not in parent:
                        parent['children'] = []
                    parent['children'].append(menu)
        
        return tree
    
    def get_topmenus(self) -> List[str]:
        """
        获取顶级菜单名称列表（兼容旧接口）
        
        Returns:
            顶级菜单名称列表
        """
        menu_tree = self.get_menu_tree()
        return [m['menu_name'] for m in menu_tree if m.get('menu_level') == 1]
    
    def get_usermenus(self, ignore: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        获取用户菜单（兼容旧接口格式）
        
        Args:
            ignore: 要忽略的菜单代码列表
            
        Returns:
            格式化的菜单列表
        """
        menu_tree = self.get_menu_tree()
        result = []
        
        for menu in menu_tree:
            if ignore and menu.get('menu_code') in ignore:
                continue
            
            # 构建兼容格式的菜单项
            path = menu.get('path') or ''
            menu_item = {
                'name': menu['menu_name'],
                'page': path.lstrip('/'),
                'icon': menu.get('icon', ''),
                'level': menu.get('menu_level', 1),
            }
            
            # 处理子菜单
            children = menu.get('children', [])
            if children:
                menu_item['list'] = []
                for child in children:
                    if ignore and child.get('menu_code') in ignore:
                        continue
                    child_path = child.get('path') or ''
                    menu_item['list'].append({
                        'name': child['menu_name'],
                        'page': child_path.lstrip('/'),
                        'icon': child.get('icon', ''),
                        'level': child.get('menu_level', 2),
                    })
            
            result.append(menu_item)
        
        return result
    
    def can_access_menu(self, menu_code: str) -> bool:
        """
        检查是否可以访问指定菜单
        
        Args:
            menu_code: 菜单代码
            
        Returns:
            是否可以访问
        """
        if self.is_superadmin:
            return True
        return rbac_service.check_menu_access(self.id, menu_code)
    
    # ========== 角色相关 ==========
    
    def get_roles(self) -> List[Dict[str, Any]]:
        """
        获取用户的角色列表
        
        Returns:
            角色字典列表
        """
        if not self._user:
            return []
        
        # 使用服务层获取角色，避免会话分离问题
        try:
            roles = rbac_service.get_user_roles(self.id)
            return [role.to_dict() for role in roles]
        except Exception:
            # 如果失败，尝试直接访问（可能在同一会话中）
            try:
                return [role.to_dict() for role in self._user.roles]
            except Exception:
                return []
    
    # ========== 类方法 ==========
    
    @classmethod
    def get(cls, user_id: int) -> Optional['User']:
        """
        根据ID获取用户
        
        Args:
            user_id: 用户ID
            
        Returns:
            User实例或None
        """
        if user_id is None:
            return None
        
        user = rbac_service.get_user_by_id(user_id)
        if user:
            return cls(user)
        return None
    
    @classmethod
    def get_by_username(cls, username: str) -> Optional['User']:
        """
        根据用户名获取用户
        
        Args:
            username: 用户名
            
        Returns:
            User实例或None
        """
        user = rbac_service.get_user_by_username(username)
        if user:
            return cls(user)
        return None
    
    def get_user(self, username: str) -> Optional['User']:
        """
        根据用户名获取用户（实例方法，兼容旧接口）
        
        Args:
            username: 用户名
            
        Returns:
            User实例或None
        """
        return self.get_by_username(username)
    
    @classmethod
    def authenticate(cls, username: str, password: str,
                     login_ip: str = None, user_agent: str = None) -> tuple:
        """
        用户认证
        
        Args:
            username: 用户名
            password: 密码
            login_ip: 登录IP
            user_agent: 用户代理
            
        Returns:
            (是否成功, User实例或错误消息)
        """
        success, result = rbac_service.authenticate_user(
            username, password, login_ip, user_agent
        )
        
        if success:
            return True, cls(result)
        return False, result
    
    @classmethod
    def create(cls, username: str, password: str, 
               email: str = None, nickname: str = None,
               role_ids: List[int] = None) -> tuple:
        """
        创建用户
        
        Args:
            username: 用户名
            password: 密码
            email: 邮箱
            nickname: 昵称
            role_ids: 角色ID列表
            
        Returns:
            (是否成功, User实例或错误消息)
        """
        success, result = rbac_service.create_user(
            username=username,
            password=password,
            email=email,
            nickname=nickname,
            role_ids=role_ids or []
        )
        
        if success:
            return True, cls(result)
        return False, result
    
    @classmethod
    def get_all_users(cls) -> List['User']:
        """
        获取所有用户
        
        Returns:
            User实例列表
        """
        users, _ = rbac_service.get_users(page=1, page_size=1000)
        return [cls(user) for user in users]
    
    @classmethod
    def delete(cls, user_id: int) -> bool:
        """
        删除用户
        
        Args:
            user_id: 用户ID
            
        Returns:
            是否成功
        """
        success, _ = rbac_service.delete_user(user_id)
        return success
    
    @classmethod
    def assign_roles(cls, user_id: int, role_ids: List[int]) -> bool:
        """
        为用户分配角色
        
        Args:
            user_id: 用户ID
            role_ids: 角色ID列表
            
        Returns:
            是否成功
        """
        success, _ = rbac_service.assign_roles_to_user(user_id, role_ids)
        return success
    
    @classmethod
    def change_password(cls, user_id: int, old_password: str, new_password: str) -> tuple:
        """
        修改密码
        
        Args:
            user_id: 用户ID
            old_password: 旧密码
            new_password: 新密码
            
        Returns:
            (是否成功, 消息)
        """
        return rbac_service.change_password(user_id, old_password, new_password)
    
    @classmethod
    def reset_password(cls, user_id: int, new_password: str) -> tuple:
        """
        重置密码
        
        Args:
            user_id: 用户ID
            new_password: 新密码
            
        Returns:
            (是否成功, 消息)
        """
        return rbac_service.reset_password(user_id, new_password)
    
    # ========== 便捷方法 ==========
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典
        
        Returns:
            用户信息字典
        """
        if not self._user:
            return {}
        
        return {
            'id': self.id,
            'username': self.username,
            'nickname': self.nickname,
            'email': self.email,
            'avatar': self.avatar,
            'is_admin': self.is_admin,
            'is_superadmin': self.is_superadmin,
            'level': self.level,
            'status': self.status,
            'roles': self.get_roles(),
            'permissions': self.get_permissions(),
        }

    def get_services(self) -> Dict[str, Dict[str, Any]]:
        """
        获取服务配置（兼容旧接口）
        
        Returns:
            服务配置字典
        """
        return SERVICE_CONF

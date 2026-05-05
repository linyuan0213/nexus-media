"""
RBAC Service Layer
基于角色的访问控制(RBAC)业务逻辑层
处理用户认证、授权、权限检查等业务逻辑
"""
from datetime import datetime
from typing import List, Optional, Dict, Any, Set
from functools import wraps

from app.utils.security import generate_password_hash, check_password_hash

from app.db.repositories.rbac_repo_adapter import (
    RBACUserRepositoryAdapter,
    RBACRoleRepositoryAdapter,
    RBACPermissionRepositoryAdapter,
    RBACMenuRepositoryAdapter,
    RBACLogRepositoryAdapter,
)
from app.db.models.rbac import RBACUser, RBACRole, RBACPermission, RBACMenu
import log


class RBACService:
    """
    RBAC服务类
    提供用户管理、角色管理、权限管理、菜单管理等业务功能
    """
    
    def __init__(self,
                 user_repo=None,
                 role_repo=None,
                 permission_repo=None,
                 menu_repo=None,
                 log_repo=None):
        self.user_repo = user_repo or RBACUserRepositoryAdapter()
        self.role_repo = role_repo or RBACRoleRepositoryAdapter()
        self.permission_repo = permission_repo or RBACPermissionRepositoryAdapter()
        self.menu_repo = menu_repo or RBACMenuRepositoryAdapter()
        self.log_repo = log_repo or RBACLogRepositoryAdapter()
    
    # ==================== 用户认证 ====================
    
    def authenticate_user(self, username: str, password: str, 
                          login_ip: Optional[str] = None,
                          user_agent: Optional[str] = None) -> tuple:
        """
        用户认证
        
        Args:
            username: 用户名
            password: 明文密码
            login_ip: 登录IP
            user_agent: 用户代理
            
        Returns:
            (是否成功, 用户对象或错误信息)
        """
        user = self.user_repo.get_user_by_username(username)
        
        if not user:
            # 记录登录失败日志（用户不存在时 user_id 为 None）
            self.log_repo.add_login_log(
                user_id=None,
                username=username,
                login_ip=login_ip,
                user_agent=user_agent,
                login_status=0,
                fail_reason='用户不存在'
            )
            return False, '用户名或密码错误'
        
        if user.STATUS != 1:
            self.log_repo.add_login_log(
                user_id=user.ID,
                username=username,
                login_ip=login_ip,
                user_agent=user_agent,
                login_status=0,
                fail_reason='用户已被禁用'
            )
            return False, '用户已被禁用'
        
        if not user.PASSWORD_HASH:
            # 密码为空，使用配置文件中的默认密码作为首次登录密码
            from config import Config
            default_password = Config().get_config('app').get('login_password') or 'password'
            if password != default_password:
                self.log_repo.add_login_log(
                    user_id=user.ID,
                    username=username,
                    login_ip=login_ip,
                    user_agent=user_agent,
                    login_status=0,
                    fail_reason='密码错误'
                )
                return False, '用户名或密码错误'
            # 首次登录成功，自动迁移为 Argon2 哈希
            new_hash = generate_password_hash(password)
            self.user_repo.update_user(user.ID, PASSWORD_HASH=new_hash)
        elif not check_password_hash(user.PASSWORD_HASH, password):
            self.log_repo.add_login_log(
                user_id=user.ID,
                username=username,
                login_ip=login_ip,
                user_agent=user_agent,
                login_status=0,
                fail_reason='密码错误'
            )
            return False, '用户名或密码错误'
        
        # 更新最后登录时间
        self.user_repo.update_last_login(user.ID, login_ip)
        
        # 记录登录成功日志
        self.log_repo.add_login_log(
            user_id=user.ID,
            username=username,
            login_ip=login_ip,
            user_agent=user_agent,
            login_status=1
        )
        
        return True, user
    
    def change_password(self, user_id: int, old_password: str, 
                        new_password: str) -> tuple:
        """
        修改密码
        
        Args:
            user_id: 用户ID
            old_password: 旧密码
            new_password: 新密码
            
        Returns:
            (是否成功, 消息)
        """
        user = self.user_repo.get_user_by_id(user_id)
        if not user:
            return False, '用户不存在'
        
        if not check_password_hash(user.PASSWORD_HASH, old_password):
            return False, '原密码错误'
        
        new_password_hash = generate_password_hash(new_password)
        success = self.user_repo.update_user(user_id, PASSWORD_HASH=new_password_hash)
        
        if success:
            return True, '密码修改成功'
        return False, '密码修改失败'
    
    def reset_password(self, user_id: int, new_password: str, old_password: Optional[str] = None) -> tuple:
        """
        重置密码

        Args:
            user_id: 用户ID
            new_password: 新密码
            old_password: 旧密码（个人修改时必填，管理员重置时可不传）

        Returns:
            (是否成功, 消息)
        """
        user = self.user_repo.get_user_by_id(user_id)
        if not user:
            return False, '用户不存在'

        # 如果提供了旧密码，则验证旧密码
        if old_password is not None:
            # 密码为空时使用默认密码
            if not user.PASSWORD_HASH:
                from config import Config
                default_password = Config().get_config('app').get('login_password') or 'password'
                if old_password != default_password:
                    return False, '旧密码错误'
            elif not check_password_hash(user.PASSWORD_HASH, old_password):
                return False, '旧密码错误'

        new_password_hash = generate_password_hash(new_password)
        success = self.user_repo.update_user(user_id, PASSWORD_HASH=new_password_hash)

        if success:
            return True, '密码修改成功'
        return False, '密码修改失败'
    
    # ==================== 用户管理 ====================
    
    def create_user(self, username: str, password: str,
                    email: Optional[str] = None,
                    nickname: Optional[str] = None,
                    role_ids: Optional[List[int]] = None,
                    is_superadmin: int = 0) -> tuple:
        """
        创建用户
        
        Args:
            username: 用户名
            password: 明文密码
            email: 邮箱
            nickname: 昵称
            role_ids: 角色ID列表
            is_superadmin: 是否为超级管理员
            
        Returns:
            (是否成功, 用户对象或错误信息)
        """
        # 检查用户名是否已存在
        if self.user_repo.is_user_exists(username):
            return False, '用户名已存在'
        
        # 检查邮箱是否已存在（空字符串视为 None）
        if email and email.strip() and self.user_repo.is_email_exists(email):
            return False, '邮箱已被使用'
        
        # 如果邮箱为空，设为 None
        if not email or not email.strip():
            email = None
        
        # 加密密码
        password_hash = generate_password_hash(password)
        
        # 创建用户
        user = self.user_repo.create_user(
            username=username,
            password_hash=password_hash,
            email=email,
            nickname=nickname,
            is_superadmin=is_superadmin
        )
        
        # 检查用户是否成功创建（处理装饰器返回值）
        if not user or isinstance(user, bool):
            # 重新查询用户
            user = self.user_repo.get_user_by_username(username)
            if not user:
                return False, '用户创建失败'
        
        # 分配角色
        if role_ids:
            self.user_repo.assign_roles_to_user(user.ID, role_ids)
        
        log.info(f"【RBAC】创建用户成功: {username}")
        return True, user
    
    def update_user(self, user_id: int, **kwargs) -> tuple:
        """
        更新用户信息
        
        Args:
            user_id: 用户ID
            **kwargs: 要更新的字段
            
        Returns:
            (是否成功, 消息)
        """
        user = self.user_repo.get_user_by_id(user_id)
        if not user:
            return False, '用户不存在'
        
        # 如果更新邮箱，检查是否已被使用
        if 'email' in kwargs and kwargs['email'] != user.EMAIL:
            if self.user_repo.is_email_exists(kwargs['email']):
                return False, '邮箱已被使用'
        
        success = self.user_repo.update_user(user_id, **kwargs)
        
        if success:
            return True, '更新成功'
        return False, '更新失败'
    
    def delete_user(self, user_id: int) -> tuple:
        """
        删除用户
        
        Args:
            user_id: 用户ID
            
        Returns:
            (是否成功, 消息)
        """
        user = self.user_repo.get_user_by_id(user_id)
        if not user:
            return False, '用户不存在'
        
        # 软删除
        success = self.user_repo.delete_user(user_id)
        
        if success:
            log.info(f"【RBAC】删除用户: {user.USERNAME}")
            return True, '删除成功'
        return False, '删除失败'
    
    def get_user_by_id(self, user_id: int) -> Optional[RBACUser]:
        """
        根据ID获取用户
        """
        return self.user_repo.get_user_by_id(user_id)
    
    def get_user_by_username(self, username: str) -> Optional[RBACUser]:
        """
        根据用户名获取用户
        """
        return self.user_repo.get_user_by_username(username)
    
    def get_users(self, page: int = 1, page_size: int = 20) -> tuple:
        """
        获取用户列表

        Returns:
            (用户列表, 总数)
        """
        return self.user_repo.get_users(page=page, page_size=page_size)
    
    def assign_roles_to_user(self, user_id: int, role_ids: List[int]) -> tuple:
        """
        为用户分配角色
        
        Args:
            user_id: 用户ID
            role_ids: 角色ID列表
            
        Returns:
            (是否成功, 消息)
        """
        user = self.user_repo.get_user_by_id(user_id)
        if not user:
            return False, '用户不存在'
        
        success = self.user_repo.assign_roles_to_user(user_id, role_ids)
        if success:
            return True, '角色分配成功'
        return False, '角色分配失败'
    
    def get_user_roles(self, user_id: int):
        """
        获取用户的角色列表
        
        Args:
            user_id: 用户ID
            
        Returns:
            角色列表
        """
        user = self.user_repo.get_user_by_id(user_id)
        if not user:
            return []
        return self.user_repo.get_user_roles(user_id)
    
    # ==================== 角色管理 ====================
    
    def create_role(self, role_name: str, role_code: str,
                    description: Optional[str] = None,
                    role_level: int = 100,
                    permission_ids: Optional[List[int]] = None,
                    menu_ids: Optional[List[int]] = None) -> tuple:
        """
        创建角色
        
        Args:
            role_name: 角色名称
            role_code: 角色代码
            description: 角色描述
            role_level: 角色级别
            permission_ids: 权限ID列表
            menu_ids: 菜单ID列表
            
        Returns:
            (是否成功, 角色对象或错误信息)
        """
        if self.role_repo.is_role_exists(role_code):
            return False, '角色代码已存在'
        if self.role_repo.is_role_name_exists(role_name):
            return False, '角色名称已存在'

        role = self.role_repo.create_role(
            role_name=role_name,
            role_code=role_code,
            description=description,
            role_level=role_level
        )

        if not role:
            return False, '创建角色失败，请检查数据是否重复'

        # 分配权限
        if permission_ids:
            self.role_repo.assign_permissions_to_role(role.id, permission_ids)

        # 分配菜单
        if menu_ids:
            self.role_repo.assign_menus_to_role(role.id, menu_ids)

        log.info(f"【RBAC】创建角色成功: {role_name}")
        return True, role
    
    def update_role(self, role_id: int, **kwargs) -> tuple:
        """
        更新角色信息
        
        Args:
            role_id: 角色ID
            **kwargs: 要更新的字段
            
        Returns:
            (是否成功, 消息)
        """
        role = self.role_repo.get_role_by_id(role_id)
        if not role:
            return False, '角色不存在'
        
        success = self.role_repo.update_role(role_id, **kwargs)
        
        if success:
            return True, '更新成功'
        return False, '更新失败'
    
    def delete_role(self, role_id: int) -> tuple:
        """
        删除角色
        
        Args:
            role_id: 角色ID
            
        Returns:
            (是否成功, 消息)
        """
        role = self.role_repo.get_role_by_id(role_id)
        if not role:
            return False, '角色不存在'
        
        success = self.role_repo.delete_role(role_id)
        
        if success:
            log.info(f"【RBAC】删除角色: {role.ROLE_NAME}")
            return True, '删除成功'
        return False, '删除失败'
    
    def get_role_by_id(self, role_id: int) -> Optional[RBACRole]:
        """
        根据ID获取角色
        """
        return self.role_repo.get_role_by_id(role_id)
    
    def get_all_roles(self) -> List[RBACRole]:
        """
        获取所有角色
        """
        return self.role_repo.get_all_roles(status=1)
    
    def assign_permissions_to_role(self, role_id: int, permission_ids: List[int]) -> tuple:
        """
        为角色分配权限
        
        Args:
            role_id: 角色ID
            permission_ids: 权限ID列表
            
        Returns:
            (是否成功, 消息)
        """
        role = self.role_repo.get_role_by_id(role_id)
        if not role:
            return False, '角色不存在'
        
        success = self.role_repo.assign_permissions_to_role(role_id, permission_ids)
        if success:
            return True, '权限分配成功'
        return False, '权限分配失败'
    
    def assign_menus_to_role(self, role_id: int, menu_ids: List[int]) -> tuple:
        """
        为角色分配菜单
        
        Args:
            role_id: 角色ID
            menu_ids: 菜单ID列表
            
        Returns:
            (是否成功, 消息)
        """
        role = self.role_repo.get_role_by_id(role_id)
        if not role:
            return False, '角色不存在'
        
        success = self.role_repo.assign_menus_to_role(role_id, menu_ids)
        if success:
            return True, '菜单分配成功'
        return False, '菜单分配失败'
    
    # ==================== 权限管理 ====================
    
    def create_permission(self, permission_name: str, permission_code: str,
                          permission_type: str = 'api',
                          module: Optional[str] = None,
                          description: Optional[str] = None) -> tuple:
        """
        创建权限
        
        Args:
            permission_name: 权限名称
            permission_code: 权限代码
            permission_type: 权限类型
            module: 所属模块
            description: 描述
            
        Returns:
            (是否成功, 权限对象或错误信息)
        """
        existing = self.permission_repo.get_permission_by_code(permission_code)
        if existing:
            return False, '权限代码已存在'
        
        permission = self.permission_repo.create_permission(
            permission_name=permission_name,
            permission_code=permission_code,
            permission_type=permission_type,
            module=module,
            description=description
        )
        
        log.info(f"【RBAC】创建权限成功: {permission_name}")
        return True, permission
    
    def update_permission(self, permission_id: int, **kwargs) -> tuple:
        """
        更新权限
        """
        permission = self.permission_repo.get_permission_by_id(permission_id)
        if not permission:
            return False, '权限不存在'
        
        success = self.permission_repo.update_permission(permission_id, **kwargs)
        if success:
            return True, '更新成功'
        return False, '更新失败'
    
    def delete_permission(self, permission_id: int) -> tuple:
        """
        删除权限
        """
        permission = self.permission_repo.get_permission_by_id(permission_id)
        if not permission:
            return False, '权限不存在'
        
        success = self.permission_repo.delete_permission(permission_id)
        if success:
            log.info(f"【RBAC】删除权限: {permission.PERMISSION_NAME}")
            return True, '删除成功'
        return False, '删除失败'
    
    def get_all_permissions(self, module: Optional[str] = None) -> List[RBACPermission]:
        """
        获取所有权限
        """
        return self.permission_repo.get_all_permissions(module=module)
    
    # ==================== 菜单管理 ====================
    
    def create_menu(self, menu_name: str, menu_code: str,
                    parent_id: Optional[int] = None,
                    path: Optional[str] = None,
                    icon: Optional[str] = None,
                    component: Optional[str] = None,
                    sort_order: int = 0,
                    menu_level: int = 1,
                    permission_code: Optional[str] = None,
                    **kwargs) -> tuple:
        """
        创建菜单
        
        Args:
            menu_name: 菜单名称
            menu_code: 菜单代码
            parent_id: 父菜单ID
            path: 路由路径
            icon: 图标
            component: 组件路径
            sort_order: 排序号
            menu_level: 菜单级别
            permission_code: 关联权限代码
            **kwargs: Vben 扩展字段等
            
        Returns:
            (是否成功, 菜单对象或错误信息)
        """
        existing = self.menu_repo.get_menu_by_code(menu_code)
        if existing:
            return False, '菜单代码已存在'
        
        menu = self.menu_repo.create_menu(
            menu_name=menu_name,
            menu_code=menu_code,
            parent_id=parent_id,
            path=path,
            icon=icon,
            component=component,
            sort_order=sort_order,
            menu_level=menu_level,
            permission_code=permission_code,
            **kwargs
        )
        
        log.info(f"【RBAC】创建菜单成功: {menu_name}")
        return True, menu
    
    def update_menu(self, menu_id: int, **kwargs) -> tuple:
        """
        更新菜单
        """
        menu = self.menu_repo.get_menu_by_id(menu_id)
        if not menu:
            return False, '菜单不存在'
        
        success = self.menu_repo.update_menu(menu_id, **kwargs)
        if success:
            return True, '更新成功'
        return False, '更新失败'
    
    def delete_menu(self, menu_id: int) -> tuple:
        """
        删除菜单
        """
        menu = self.menu_repo.get_menu_by_id(menu_id)
        if not menu:
            return False, '菜单不存在'
        
        success = self.menu_repo.delete_menu(menu_id)
        if success:
            log.info(f"【RBAC】删除菜单: {menu.MENU_NAME}")
            return True, '删除成功'
        return False, '删除失败'
    
    def get_menu_tree(self, include_hidden: bool = False) -> List[Dict[str, Any]]:
        """
        获取菜单树形结构
        
        Args:
            include_hidden: 是否包含隐藏的菜单
        """
        return self.menu_repo.get_menu_tree(include_hidden=include_hidden)
    
    def get_user_menus(self, user_id: int) -> List[dict]:
        """
        获取用户的菜单树（Vben 格式）
        超级管理员返回所有菜单
        """
        user = self.get_user_by_id(user_id)
        if user and user.is_superadmin:
            menus = self.menu_repo.get_all_menus()
        else:
            menus = self.menu_repo.get_user_menus(user_id)

        # 补全父级菜单
        menu_ids = {m.ID for m in menus}
        all_menus = list(menus)
        for m in menus:
            pid = m.PARENT_ID
            while pid:
                parent = self.menu_repo.get_menu_by_id(pid)
                if parent and parent.ID not in menu_ids:
                    menu_ids.add(parent.ID)
                    all_menus.append(parent)
                pid = parent.PARENT_ID if parent else None

        all_menus.sort(key=lambda x: x.SORT_ORDER)

        def _to_vben_node(menu):
            meta = {"title": menu.MENU_NAME}
            if menu.ICON:
                meta["icon"] = menu.ICON
            if menu.SORT_ORDER is not None:
                meta["order"] = menu.SORT_ORDER
            if menu.PERMISSION_CODE:
                meta["authority"] = [menu.PERMISSION_CODE]
            if getattr(menu, 'HIDE_IN_MENU', 0):
                meta["hideInMenu"] = True
            if getattr(menu, 'STATUS', 1) == 0:
                meta["menuVisibleWithForbidden"] = True
            # path 必须唯一，否则 Vben menu 组件会用 path 作为 key 导致多个菜单联动
            # 注意：空字符串/None 都会 fallback 到 MENU_CODE，确保菜单 key 唯一
            # 保留前导 "/" 作为绝对路径，避免 Vben 导航时拼接成 /plugin/plugin/xxx
            path_val = menu.PATH or menu.MENU_CODE
            node = {
                "path": path_val.lower(),
                "name": menu.MENU_CODE,
                "meta": meta,
            }
            if menu.COMPONENT:
                node["component"] = menu.COMPONENT
            if getattr(menu, 'REDIRECT', None):
                node["redirect"] = menu.REDIRECT
            return node

        menu_map = {m.ID: _to_vben_node(m) for m in all_menus}
        pid_map = {}
        for m in all_menus:
            pid = m.PARENT_ID
            if pid not in pid_map:
                pid_map[pid] = []
            pid_map[pid].append(m.ID)

        def _build_tree(parent_id=None, parent_disabled=False):
            result = []
            for mid in pid_map.get(parent_id, []):
                node = dict(menu_map[mid])
                # 继承父级禁用状态：父菜单被禁用时，所有子菜单也标记为禁用
                is_disabled = parent_disabled or node.get('meta', {}).get('menuVisibleWithForbidden', False)
                if is_disabled:
                    node.setdefault('meta', {})['menuVisibleWithForbidden'] = True
                children = _build_tree(mid, is_disabled)
                if children:
                    node["children"] = children
                result.append(node)
            return result

        return _build_tree()
    
    # ==================== 权限检查 ====================
    
    def get_user_permissions(self, user_id: int) -> Set[str]:
        """
        获取用户的所有权限代码
        
        Args:
            user_id: 用户ID
            
        Returns:
            权限代码集合
        """
        user = self.user_repo.get_user_by_id(user_id)
        if not user:
            return set()
        
        # 超级管理员拥有所有权限
        if user.is_superadmin == 1:
            all_permissions = self.permission_repo.get_all_permissions()
            return {p.permission_code for p in all_permissions}
        
        permissions = set()
        roles = self.user_repo.get_user_roles(user_id)
        for role in roles:
            if role.status == 1:
                role_permissions = self.role_repo.get_role_permissions(role.id)
                for perm in role_permissions:
                    if perm.status == 1:
                        permissions.add(perm.permission_code)
        
        return permissions
    
    def check_permission(self, user_id: int, permission_code: str) -> bool:
        """
        检查用户是否拥有指定权限
        
        Args:
            user_id: 用户ID
            permission_code: 权限代码
            
        Returns:
            是否拥有权限
        """
        user = self.user_repo.get_user_by_id(user_id)
        if not user:
            return False
        
        # 超级管理员拥有所有权限
        if user.IS_SUPERADMIN == 1:
            return True
        
        permissions = self.get_user_permissions(user_id)
        return permission_code in permissions
    
    def check_any_permission(self, user_id: int, permission_codes: List[str]) -> bool:
        """
        检查用户是否拥有任一指定权限
        
        Args:
            user_id: 用户ID
            permission_codes: 权限代码列表
            
        Returns:
            是否拥有任一权限
        """
        user = self.user_repo.get_user_by_id(user_id)
        if not user:
            return False
        
        # 超级管理员拥有所有权限
        if user.IS_SUPERADMIN == 1:
            return True
        
        permissions = self.get_user_permissions(user_id)
        return any(code in permissions for code in permission_codes)
    
    def check_all_permissions(self, user_id: int, permission_codes: List[str]) -> bool:
        """
        检查用户是否拥有所有指定权限
        
        Args:
            user_id: 用户ID
            permission_codes: 权限代码列表
            
        Returns:
            是否拥有所有权限
        """
        user = self.user_repo.get_user_by_id(user_id)
        if not user:
            return False
        
        # 超级管理员拥有所有权限
        if user.IS_SUPERADMIN == 1:
            return True
        
        permissions = self.get_user_permissions(user_id)
        return all(code in permissions for code in permission_codes)
    
    def check_menu_access(self, user_id: int, menu_code: str) -> bool:
        """
        检查用户是否有权访问指定菜单
        
        Args:
            user_id: 用户ID
            menu_code: 菜单代码
            
        Returns:
            是否有权访问
        """
        user = self.user_repo.get_user_by_id(user_id)
        if not user:
            return False
        
        # 超级管理员可以访问所有菜单
        if user.IS_SUPERADMIN == 1:
            return True
        
        # 获取用户的所有菜单
        user_menus = self.menu_repo.get_user_menus(user_id)
        menu_codes = {m.MENU_CODE for m in user_menus}
        
        return menu_code in menu_codes


# 全局RBAC服务实例
rbac_service = RBACService()


def require_permission(permission_code: str):
    """
    权限检查装饰器（向后兼容，内部逻辑已迁移到 FastAPI deps）
    
    Args:
        permission_code: 需要的权限代码
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator


def require_any_permission(permission_codes: List[str]):
    """
    任一权限检查装饰器（向后兼容，内部逻辑已迁移到 FastAPI deps）
    
    Args:
        permission_codes: 需要的权限代码列表（满足任一即可）
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator

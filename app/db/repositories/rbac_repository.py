"""
RBAC Repository
基于角色的访问控制(RBAC)数据访问层
处理用户、角色、权限、菜单的数据库操作
"""

from datetime import datetime
from typing import Any

from sqlalchemy import and_, desc
from sqlalchemy.orm import selectinload

from app.db import DbPersist
from app.db.models.rbac import RBACMenu, RBACOperationLog, RBACPermission, RBACRole, RBACUser, RBACUserLoginLog
from app.db.repositories.base_repository import BaseRepository


class RBACUserRepository(BaseRepository):
    """
    RBAC用户管理仓储
    """

    def get_user_by_id(self, user_id: int) -> RBACUser | None:
        """
        根据ID获取用户（预加载角色）

        Args:
            user_id: 用户ID

        Returns:
            用户对象或None
        """
        return (
            self._db.query(RBACUser)
            .options(
                selectinload(RBACUser.roles),
            )
            .filter(user_id == RBACUser.ID)
            .first()
        )

    def get_user_by_username(self, username: str) -> RBACUser | None:
        """
        根据用户名获取用户（不过滤状态，让上层判断）

        Args:
            username: 用户名

        Returns:
            用户对象或None
        """
        return self._db.query(RBACUser).filter(username == RBACUser.USERNAME).first()

    def get_user_by_email(self, email: str) -> RBACUser | None:
        """
        根据邮箱获取用户

        Args:
            email: 邮箱地址

        Returns:
            用户对象或None
        """
        return self._db.query(RBACUser).filter(and_(RBACUser.EMAIL == email, RBACUser.STATUS == 1)).first()

    def get_users(self, page: int = 1, page_size: int = 20, status: int | None = None) -> tuple:
        """
        获取用户列表（支持分页，预加载角色）

        Args:
            page: 页码
            page_size: 每页数量
            status: 状态筛选

        Returns:
            (用户列表, 总数)
        """
        query = self._db.query(RBACUser).options(
            selectinload(RBACUser.roles),
        )

        if status is not None:
            query = query.filter(status == RBACUser.STATUS)

        total = query.count()
        users = query.offset((page - 1) * page_size).limit(page_size).all()

        return users, total

    def get_all_users(self) -> list[RBACUser]:
        """
        获取所有用户（预加载角色）

        Returns:
            用户列表
        """
        return (
            self._db.query(RBACUser)
            .options(
                selectinload(RBACUser.roles),
            )
            .filter(RBACUser.STATUS == 1)
            .all()
        )

    def is_user_exists(self, username: str) -> bool:
        """
        检查用户名是否已存在

        Args:
            username: 用户名

        Returns:
            是否存在
        """
        count = self._db.query(RBACUser).filter(username == RBACUser.USERNAME).count()
        return count > 0

    def is_email_exists(self, email: str) -> bool:
        """
        检查邮箱是否已存在

        Args:
            email: 邮箱地址

        Returns:
            是否存在
        """
        count = self._db.query(RBACUser).filter(email == RBACUser.EMAIL).count()
        return count > 0

    @DbPersist(BaseRepository._db)
    def create_user(
        self,
        username: str,
        password_hash: str,
        email: str | None = None,
        nickname: str | None = None,
        is_superadmin: int = 0,
    ) -> RBACUser:
        """
        创建新用户

        Args:
            username: 用户名
            password_hash: 密码哈希
            email: 邮箱
            nickname: 昵称
            is_superadmin: 是否为超级管理员

        Returns:
            创建的用户对象
        """
        user = RBACUser(
            USERNAME=username,
            PASSWORD_HASH=password_hash,
            EMAIL=email,
            NICKNAME=nickname or username,
            IS_SUPERADMIN=is_superadmin,
            STATUS=1,
        )
        self._db.insert(user)
        return user

    @DbPersist(BaseRepository._db)
    def update_user(self, user_id: int, **kwargs) -> bool:
        """
        更新用户信息

        Args:
            user_id: 用户ID
            **kwargs: 要更新的字段

        Returns:
            是否成功
        """
        user = self.get_user_by_id(user_id)
        if not user:
            return False

        allowed_fields = ["EMAIL", "NICKNAME", "AVATAR", "STATUS", "PASSWORD_HASH"]
        for key, value in kwargs.items():
            if key.upper() in allowed_fields:
                setattr(user, key.upper(), value)

        user.UPDATED_AT = datetime.now()
        return True

    @DbPersist(BaseRepository._db)
    def update_last_login(self, user_id: int, ip: str | None = None) -> bool:
        """
        更新用户最后登录时间

        Args:
            user_id: 用户ID
            ip: 登录IP

        Returns:
            是否成功
        """
        user = self.get_user_by_id(user_id)
        if not user:
            return False

        user.LAST_LOGIN_AT = datetime.now()
        if ip:
            user.LAST_LOGIN_IP = ip
        return True

    @DbPersist(BaseRepository._db)
    def delete_user(self, user_id: int) -> bool:
        """
        删除用户（硬删除）

        Args:
            user_id: 用户ID

        Returns:
            是否成功
        """
        result = self._db.query(RBACUser).filter(user_id == RBACUser.ID).delete()
        return result > 0

    @DbPersist(BaseRepository._db)
    def hard_delete_user(self, user_id: int) -> bool:
        """
        硬删除用户

        Args:
            user_id: 用户ID

        Returns:
            是否成功
        """
        result = self._db.query(RBACUser).filter(user_id == RBACUser.ID).delete()
        return result > 0

    # ========== 用户角色关联操作 ==========

    def get_user_roles(self, user_id: int) -> list[RBACRole]:
        """
        获取用户的角色列表

        Args:
            user_id: 用户ID

        Returns:
            角色列表
        """
        user = self.get_user_by_id(user_id)
        if not user:
            return []
        return user.roles

    @DbPersist(BaseRepository._db)
    def assign_roles_to_user(self, user_id: int, role_ids: list[int]) -> bool:
        """
        为用户分配角色

        Args:
            user_id: 用户ID
            role_ids: 角色ID列表

        Returns:
            是否成功
        """
        user = self.get_user_by_id(user_id)
        if not user:
            return False

        # 获取角色对象
        roles = self._db.query(RBACRole).filter(RBACRole.ID.in_(role_ids), RBACRole.STATUS == 1).all()

        # 清空现有角色并分配新角色
        user.roles = roles
        return True

    @DbPersist(BaseRepository._db)
    def add_role_to_user(self, user_id: int, role_id: int) -> bool:
        """
        为用户添加单个角色

        Args:
            user_id: 用户ID
            role_id: 角色ID

        Returns:
            是否成功
        """
        user = self.get_user_by_id(user_id)
        role = self._db.query(RBACRole).filter(role_id == RBACRole.ID).first()

        if not user or not role:
            return False

        if role not in user.roles:
            user.roles.append(role)

        return True

    @DbPersist(BaseRepository._db)
    def remove_role_from_user(self, user_id: int, role_id: int) -> bool:
        """
        移除用户的角色

        Args:
            user_id: 用户ID
            role_id: 角色ID

        Returns:
            是否成功
        """
        user = self.get_user_by_id(user_id)
        if not user:
            return False

        user.roles = [r for r in user.roles if role_id != r.ID]
        return True


class RBACRoleRepository(BaseRepository):
    """
    RBAC角色管理仓储
    """

    def get_role_by_id(self, role_id: int) -> RBACRole | None:
        """
        根据ID获取角色

        Args:
            role_id: 角色ID

        Returns:
            角色对象或None
        """
        return self._db.query(RBACRole).filter(role_id == RBACRole.ID).first()

    def get_role_by_code(self, role_code: str) -> RBACRole | None:
        """
        根据角色代码获取角色

        Args:
            role_code: 角色代码

        Returns:
            角色对象或None
        """
        return self._db.query(RBACRole).filter(and_(RBACRole.ROLE_CODE == role_code, RBACRole.STATUS == 1)).first()

    def get_all_roles(self, status: int | None = None) -> list[RBACRole]:
        """
        获取所有角色（预加载权限、菜单、用户关联）

        Args:
            status: 状态筛选

        Returns:
            角色列表
        """
        query = self._db.query(RBACRole).options(
            selectinload(RBACRole.permissions),
            selectinload(RBACRole.menus),
            selectinload(RBACRole.users),
        )
        if status is not None:
            query = query.filter(status == RBACRole.STATUS)
        return query.order_by(RBACRole.ROLE_LEVEL).all()

    def get_roles_page(self, page: int = 1, page_size: int = 20) -> tuple:
        """
        分页获取角色列表

        Args:
            page: 页码
            page_size: 每页数量

        Returns:
            (角色列表, 总数)
        """
        query = self._db.query(RBACRole).filter(RBACRole.STATUS == 1)
        total = query.count()
        roles = query.order_by(RBACRole.ROLE_LEVEL).offset((page - 1) * page_size).limit(page_size).all()
        return roles, total

    def is_role_exists(self, role_code: str) -> bool:
        """
        检查角色代码是否已存在

        Args:
            role_code: 角色代码

        Returns:
            是否存在
        """
        count = self._db.query(RBACRole).filter(role_code == RBACRole.ROLE_CODE).count()
        return count > 0

    def is_role_name_exists(self, role_name: str) -> bool:
        """
        检查角色名称是否已存在

        Args:
            role_name: 角色名称

        Returns:
            是否存在
        """
        count = self._db.query(RBACRole).filter(role_name == RBACRole.ROLE_NAME).count()
        return count > 0

    @DbPersist(BaseRepository._db)
    def create_role(
        self, role_name: str, role_code: str, description: str | None = None, role_level: int = 100
    ) -> RBACRole:
        """
        创建角色

        Args:
            role_name: 角色名称
            role_code: 角色代码
            description: 角色描述
            role_level: 角色级别

        Returns:
            创建的角色对象
        """
        role = RBACRole(
            ROLE_NAME=role_name, ROLE_CODE=role_code, DESCRIPTION=description, ROLE_LEVEL=role_level, STATUS=1
        )
        self._db.insert(role)
        return role

    @DbPersist(BaseRepository._db)
    def update_role(self, role_id: int, **kwargs) -> bool:
        """
        更新角色信息

        Args:
            role_id: 角色ID
            **kwargs: 要更新的字段

        Returns:
            是否成功
        """
        role = self.get_role_by_id(role_id)
        if not role:
            return False

        allowed_fields = ["ROLE_NAME", "DESCRIPTION", "ROLE_LEVEL", "STATUS"]
        for key, value in kwargs.items():
            if key.upper() in allowed_fields:
                setattr(role, key.upper(), value)

        role.UPDATED_AT = datetime.now()
        return True

    @DbPersist(BaseRepository._db)
    def delete_role(self, role_id: int) -> bool:
        """
        删除角色

        Args:
            role_id: 角色ID

        Returns:
            是否成功
        """
        result = self._db.query(RBACRole).filter(role_id == RBACRole.ID).delete()
        return result > 0

    # ========== 角色权限关联操作 ==========

    def get_role_permissions(self, role_id: int) -> list[RBACPermission]:
        """
        获取角色的权限列表

        Args:
            role_id: 角色ID

        Returns:
            权限列表
        """
        role = self.get_role_by_id(role_id)
        if not role:
            return []
        return role.permissions

    @DbPersist(BaseRepository._db)
    def assign_permissions_to_role(self, role_id: int, permission_ids: list[int]) -> bool:
        """
        为角色分配权限

        Args:
            role_id: 角色ID
            permission_ids: 权限ID列表

        Returns:
            是否成功
        """
        role = self.get_role_by_id(role_id)
        if not role:
            return False

        permissions = (
            self._db.query(RBACPermission)
            .filter(RBACPermission.ID.in_(permission_ids), RBACPermission.STATUS == 1)
            .all()
        )

        role.permissions = permissions
        return True

    # ========== 角色菜单关联操作 ==========

    def get_role_menus(self, role_id: int) -> list[RBACMenu]:
        """
        获取角色的菜单列表

        Args:
            role_id: 角色ID

        Returns:
            菜单列表
        """
        role = self.get_role_by_id(role_id)
        if not role:
            return []
        return role.menus

    @DbPersist(BaseRepository._db)
    def assign_menus_to_role(self, role_id: int, menu_ids: list[int]) -> bool:
        """
        为角色分配菜单

        Args:
            role_id: 角色ID
            menu_ids: 菜单ID列表

        Returns:
            是否成功
        """
        role = self.get_role_by_id(role_id)
        if not role:
            return False

        menus = self._db.query(RBACMenu).filter(RBACMenu.ID.in_(menu_ids), RBACMenu.STATUS == 1).all()

        role.menus = menus
        return True


class RBACPermissionRepository(BaseRepository):
    """
    RBAC权限管理仓储
    """

    def get_permission_by_id(self, permission_id: int) -> RBACPermission | None:
        """
        根据ID获取权限
        """
        return self._db.query(RBACPermission).filter(permission_id == RBACPermission.ID).first()

    def get_permission_by_code(self, permission_code: str) -> RBACPermission | None:
        """
        根据权限代码获取权限
        """
        return (
            self._db.query(RBACPermission)
            .filter(and_(RBACPermission.PERMISSION_CODE == permission_code, RBACPermission.STATUS == 1))
            .first()
        )

    def get_all_permissions(
        self, module: str | None = None, permission_type: str | None = None
    ) -> list[RBACPermission]:
        """
        获取所有权限

        Args:
            module: 模块筛选
            permission_type: 权限类型筛选

        Returns:
            权限列表
        """
        query = self._db.query(RBACPermission).filter(RBACPermission.STATUS == 1)

        if module:
            query = query.filter(module == RBACPermission.MODULE)
        if permission_type:
            query = query.filter(permission_type == RBACPermission.PERMISSION_TYPE)

        return query.order_by(RBACPermission.MODULE, RBACPermission.PERMISSION_CODE).all()

    def get_permissions_by_codes(self, codes: list[str]) -> list[RBACPermission]:
        """
        根据权限代码列表获取权限
        """
        return (
            self._db.query(RBACPermission)
            .filter(and_(RBACPermission.PERMISSION_CODE.in_(codes), RBACPermission.STATUS == 1))
            .all()
        )

    @DbPersist(BaseRepository._db)
    def create_permission(
        self,
        permission_name: str,
        permission_code: str,
        permission_type: str = "api",
        module: str | None = None,
        description: str | None = None,
    ) -> RBACPermission:
        """
        创建权限
        """
        permission = RBACPermission(
            PERMISSION_NAME=permission_name,
            PERMISSION_CODE=permission_code,
            PERMISSION_TYPE=permission_type,
            MODULE=module,
            DESCRIPTION=description,
            STATUS=1,
        )
        self._db.insert(permission)
        return permission

    @DbPersist(BaseRepository._db)
    def update_permission(self, permission_id: int, **kwargs) -> bool:
        """
        更新权限信息
        """
        permission = self.get_permission_by_id(permission_id)
        if not permission:
            return False

        allowed_fields = ["PERMISSION_NAME", "DESCRIPTION", "STATUS", "MODULE"]
        for key, value in kwargs.items():
            if key.upper() in allowed_fields:
                setattr(permission, key.upper(), value)

        permission.UPDATED_AT = datetime.now()
        return True

    @DbPersist(BaseRepository._db)
    def delete_permission(self, permission_id: int) -> bool:
        """
        删除权限
        """
        result = self._db.query(RBACPermission).filter(permission_id == RBACPermission.ID).delete()
        return result > 0


class RBACMenuRepository(BaseRepository):
    """
    RBAC菜单管理仓储
    """

    def get_menu_by_id(self, menu_id: int) -> RBACMenu | None:
        """
        根据ID获取菜单
        """
        return self._db.query(RBACMenu).filter(menu_id == RBACMenu.ID).first()

    def get_menu_by_code(self, menu_code: str, include_hidden: bool = True) -> RBACMenu | None:
        """
        根据菜单代码获取菜单

        Args:
            menu_code: 菜单代码
            include_hidden: 是否包含隐藏的菜单，默认包含
        """
        query = self._db.query(RBACMenu).filter(menu_code == RBACMenu.MENU_CODE)
        if not include_hidden:
            query = query.filter(RBACMenu.STATUS == 1)
        return query.first()

    def get_all_menus(self, status: int | None = None) -> list[RBACMenu]:
        """
        获取所有菜单
        """
        query = self._db.query(RBACMenu)
        if status is not None:
            query = query.filter(status == RBACMenu.STATUS)
        return query.order_by(RBACMenu.SORT_ORDER).all()

    def get_top_menus(self, include_hidden: bool = False) -> list[RBACMenu]:
        """
        获取顶级菜单列表

        Args:
            include_hidden: 是否包含隐藏的菜单
        """
        query = self._db.query(RBACMenu).filter(RBACMenu.PARENT_ID.is_(None))
        if not include_hidden:
            query = query.filter(RBACMenu.STATUS == 1)
        return query.order_by(RBACMenu.SORT_ORDER).all()

    def get_children_menus(self, parent_id: int) -> list[RBACMenu]:
        """
        获取子菜单列表
        """
        return (
            self._db.query(RBACMenu)
            .filter(and_(RBACMenu.PARENT_ID == parent_id, RBACMenu.STATUS == 1))
            .order_by(RBACMenu.SORT_ORDER)
            .all()
        )

    def get_menu_tree(self, include_hidden: bool = False) -> list[dict[str, Any]]:
        """
        获取菜单树形结构

        Args:
            include_hidden: 是否包含隐藏的菜单
        """

        def build_tree(parent_id=None):
            query = self._db.query(RBACMenu).filter(
                parent_id == RBACMenu.PARENT_ID if parent_id is not None else RBACMenu.PARENT_ID.is_(None)
            )
            if not include_hidden:
                query = query.filter(RBACMenu.STATUS == 1)
            menus = query.order_by(RBACMenu.SORT_ORDER).all()

            result = []
            for menu in menus:
                menu_dict = menu.to_dict()
                menu_dict["children"] = build_tree(menu.ID)
                result.append(menu_dict)
            return result

        return build_tree()

    def get_user_menus(self, user_id: int) -> list[RBACMenu]:
        """
        获取用户可访问的菜单列表

        通过用户的角色关联获取菜单
        """
        from app.db.models.rbac import role_menus, user_roles

        # 获取用户的所有角色关联的菜单
        menus = (
            self._db.query(RBACMenu)
            .join(role_menus, role_menus.c.menu_id == RBACMenu.ID)
            .join(user_roles, role_menus.c.role_id == user_roles.c.role_id)
            .filter(user_roles.c.user_id == user_id)
            .distinct()
            .order_by(RBACMenu.SORT_ORDER)
            .all()
        )

        return menus

    @DbPersist(BaseRepository._db)
    def create_menu(
        self,
        menu_name: str,
        menu_code: str,
        parent_id: int | None = None,
        path: str | None = None,
        icon: str | None = None,
        component: str | None = None,
        sort_order: int = 0,
        menu_level: int = 1,
        permission_code: str | None = None,
        **kwargs,
    ) -> RBACMenu:
        """
        创建菜单
        """
        menu = RBACMenu(
            MENU_NAME=menu_name,
            MENU_CODE=menu_code,
            PARENT_ID=parent_id,
            PATH=path,
            ICON=icon,
            COMPONENT=component,
            SORT_ORDER=sort_order,
            MENU_LEVEL=menu_level,
            PERMISSION_CODE=permission_code,
            STATUS=1,
        )
        # 支持 Vben 扩展字段
        vben_fields = [
            "REDIRECT",
            "KEEP_ALIVE",
            "AFFIX_TAB",
            "HIDE_IN_MENU",
            "HIDE_IN_TAB",
            "HIDE_IN_BREADCRUMB",
            "ACTIVE_ICON",
            "BADGE",
            "BADGE_TYPE",
        ]
        for key, value in kwargs.items():
            if key.upper() in vben_fields:
                setattr(menu, key.upper(), value)
        self._db.insert(menu)
        return menu

    @DbPersist(BaseRepository._db)
    def update_menu(self, menu_id: int, **kwargs) -> bool:
        """
        更新菜单信息
        """
        menu = self.get_menu_by_id(menu_id)
        if not menu:
            return False

        allowed_fields = [
            "MENU_NAME",
            "MENU_CODE",
            "PATH",
            "ICON",
            "COMPONENT",
            "PARENT_ID",
            "SORT_ORDER",
            "IS_HIDDEN",
            "STATUS",
            "PERMISSION_CODE",
            "REDIRECT",
            "KEEP_ALIVE",
            "AFFIX_TAB",
            "HIDE_IN_MENU",
            "HIDE_IN_TAB",
            "HIDE_IN_BREADCRUMB",
            "ACTIVE_ICON",
            "BADGE",
            "BADGE_TYPE",
        ]
        for key, value in kwargs.items():
            if key.upper() in allowed_fields:
                setattr(menu, key.upper(), value)

        # 更新菜单层级
        if "parent_id" in kwargs:
            if kwargs["parent_id"] is None:
                menu.MENU_LEVEL = 1
            else:
                parent = self.get_menu_by_id(kwargs["parent_id"])
                if parent:
                    menu.MENU_LEVEL = parent.MENU_LEVEL + 1

        menu.UPDATED_AT = datetime.now()
        return True

    @DbPersist(BaseRepository._db)
    def delete_menu(self, menu_id: int) -> bool:
        """
        删除菜单（同时删除子菜单）
        """
        # 先删除子菜单
        self._db.query(RBACMenu).filter(menu_id == RBACMenu.PARENT_ID).delete()
        # 删除菜单本身
        result = self._db.query(RBACMenu).filter(menu_id == RBACMenu.ID).delete()
        return result > 0


class RBACLogRepository(BaseRepository):
    """
    RBAC日志管理仓储
    """

    # ========== 登录日志 ==========

    @DbPersist(BaseRepository._db)
    def add_login_log(
        self,
        user_id: int | None,
        username: str,
        login_ip: str | None = None,
        login_location: str | None = None,
        user_agent: str | None = None,
        login_type: str = "password",
        login_status: int = 1,
        fail_reason: str | None = None,
    ) -> RBACUserLoginLog:
        """
        添加登录日志
        """
        log = RBACUserLoginLog(
            USER_ID=user_id,
            USERNAME=username,
            LOGIN_IP=login_ip,
            LOGIN_LOCATION=login_location,
            USER_AGENT=user_agent,
            LOGIN_TYPE=login_type,
            LOGIN_STATUS=login_status,
            FAIL_REASON=fail_reason,
        )
        self._db.insert(log)
        return log

    def get_login_logs(self, user_id: int | None = None, page: int = 1, page_size: int = 20) -> tuple:
        """
        获取登录日志
        """
        query = self._db.query(RBACUserLoginLog)

        if user_id:
            query = query.filter(user_id == RBACUserLoginLog.USER_ID)

        total = query.count()
        logs = query.order_by(desc(RBACUserLoginLog.LOGIN_AT)).offset((page - 1) * page_size).limit(page_size).all()

        return logs, total

    # ========== 操作日志 ==========

    @DbPersist(BaseRepository._db)
    def add_operation_log(
        self,
        user_id: int | None = None,
        username: str | None = None,
        module: str | None = None,
        operation_type: str = "QUERY",
        description: str | None = None,
        request_method: str | None = None,
        request_url: str | None = None,
        request_params: str | None = None,
        response_data: str | None = None,
        operation_ip: str | None = None,
        execution_time: int | None = None,
        operation_status: int = 1,
        error_msg: str | None = None,
    ) -> RBACOperationLog:
        """
        添加操作日志
        """
        log = RBACOperationLog(
            USER_ID=user_id,
            USERNAME=username,
            MODULE=module,
            OPERATION_TYPE=operation_type,
            DESCRIPTION=description,
            REQUEST_METHOD=request_method,
            REQUEST_URL=request_url,
            REQUEST_PARAMS=request_params,
            RESPONSE_DATA=response_data,
            OPERATION_IP=operation_ip,
            EXECUTION_TIME=execution_time,
            OPERATION_STATUS=operation_status,
            ERROR_MSG=error_msg,
        )
        self._db.insert(log)
        return log

    def get_operation_logs(
        self, user_id: int | None = None, module: str | None = None, page: int = 1, page_size: int = 20
    ) -> tuple:
        """
        获取操作日志
        """
        query = self._db.query(RBACOperationLog)

        if user_id:
            query = query.filter(user_id == RBACOperationLog.USER_ID)
        if module:
            query = query.filter(module == RBACOperationLog.MODULE)

        total = query.count()
        logs = query.order_by(desc(RBACOperationLog.OPERATED_AT)).offset((page - 1) * page_size).limit(page_size).all()

        return logs, total

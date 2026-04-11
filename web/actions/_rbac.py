

from flask_login import current_user

from web.backend.user import User
from web.actions._base import WebActionBase


class WebActionRbacMixin:
    @staticmethod
    def _create_user(data):
        """
        创建用户（RBAC）
        """
        from web.backend.user import User

        username = data.get("username")
        password = data.get("password")
        email = data.get("email")
        nickname = data.get("nickname")
        role_ids = data.get("role_ids", [])

        if not username or not password:
            return WebActionBase._fail(success=False, message="用户名和密码不能为空")

        success, result = User.create(
            username=username,
            password=password,
            email=email,
            nickname=nickname,
            role_ids=role_ids
        )

        if success:
            return WebActionBase._success(success=True, message="创建成功", data=result.to_dict())
        return WebActionBase._fail(success=False, message=result)

    @staticmethod
    def _update_user(data):
        """
        更新用户（RBAC）
        """
        from app.services.rbac_service import rbac_service

        user_id = data.get("id")
        if not user_id:
            return WebActionBase._fail(success=False, message="用户ID不能为空")

        update_fields = {}
        for field in ["email", "nickname", "status", "avatar"]:
            if field in data:
                update_fields[field] = data[field]

        success, message = rbac_service.update_user(user_id, **update_fields)

        # 更新角色
        if "role_ids" in data:
            rbac_service.assign_roles_to_user(user_id, data["role_ids"])

        if success:
            return WebActionBase._success(success=True, message=message)
        return WebActionBase._fail(success=False, message=message)

    @staticmethod
    def _delete_user(data):
        """
        删除用户（RBAC）
        """
        from web.backend.user import User

        user_id = data.get("id")
        if not user_id:
            return WebActionBase._fail(success=False, message="用户ID不能为空")

        success = User.delete(user_id)

        if success:
            return WebActionBase._success(success=True, message="删除成功")
        return WebActionBase._fail(success=False, message="删除失败")

    @staticmethod
    def _get_user(data):
        """
        获取单个用户信息（RBAC）
        """
        from web.backend.user import User

        user_id = data.get("id")
        if not user_id:
            return WebActionBase._fail(success=False, message="用户ID不能为空")

        user = User.get(user_id)
        if user:
            return WebActionBase._success(success=True, data=user.to_dict())
        return WebActionBase._fail(success=False, message="用户不存在")

    @staticmethod
    def _reset_password(data):
        """
        重置密码（RBAC）
        """
        from web.backend.user import User

        user_id = data.get("user_id")
        new_password = data.get("new_password")

        if not user_id or not new_password:
            return WebActionBase._fail(success=False, message="用户ID和新密码不能为空")

        success, message = User.reset_password(user_id, new_password)

        if success:
            return WebActionBase._success(success=True, message=message)
        return WebActionBase._fail(success=False, message=message)

    @staticmethod
    def _create_role(data):
        """
        创建角色
        """
        from app.services.rbac_service import rbac_service

        role_name = data.get("role_name")
        role_code = data.get("role_code")

        if not role_name or not role_code:
            return WebActionBase._fail(success=False, message="角色名称和代码不能为空")

        success, result = rbac_service.create_role(
            role_name=role_name,
            role_code=role_code,
            description=data.get("description"),
            role_level=data.get("role_level", 100),
            permission_ids=data.get("permission_ids", []),
            menu_ids=data.get("menu_ids", [])
        )

        if success:
            return WebActionBase._success(success=True, message="创建成功", data=result.to_dict())
        return WebActionBase._fail(success=False, message=result)

    @staticmethod
    def _update_role(data):
        """
        更新角色
        """
        from app.services.rbac_service import rbac_service

        role_id = data.get("id")
        if not role_id:
            return WebActionBase._fail(success=False, message="角色ID不能为空")

        update_fields = {}
        for field in ["role_name", "description", "role_level", "status"]:
            if field in data:
                update_fields[field] = data[field]

        success, message = rbac_service.update_role(role_id, **update_fields)

        # 更新权限
        if "permission_ids" in data:
            rbac_service.assign_permissions_to_role(
                role_id, data["permission_ids"])

        # 更新菜单
        if "menu_ids" in data:
            rbac_service.assign_menus_to_role(role_id, data["menu_ids"])

        if success:
            return WebActionBase._success(success=True, message=message)
        return WebActionBase._fail(success=False, message=message)

    @staticmethod
    def _delete_role(data):
        """
        删除角色
        """
        from app.services.rbac_service import rbac_service

        role_id = data.get("id")
        if not role_id:
            return WebActionBase._fail(success=False, message="角色ID不能为空")

        success, message = rbac_service.delete_role(role_id)

        if success:
            return WebActionBase._success(success=True, message=message)
        return WebActionBase._fail(success=False, message=message)

    @staticmethod
    def _get_role(data):
        """
        获取单个角色信息
        """
        from app.services.rbac_service import rbac_service

        role_id = data.get("id")
        if not role_id:
            return WebActionBase._fail(success=False, message="角色ID不能为空")

        role = rbac_service.get_role_by_id(role_id)
        if role:
            return WebActionBase._success(success=True, data=role.to_dict())
        return WebActionBase._fail(success=False, message="角色不存在")

    @staticmethod
    def _create_menu(data):
        """
        创建菜单
        """
        from app.services.rbac_service import rbac_service

        menu_name = data.get("menu_name")
        menu_code = data.get("menu_code")

        if not menu_name or not menu_code:
            return WebActionBase._fail(success=False, message="菜单名称和代码不能为空")

        success, result = rbac_service.create_menu(
            menu_name=menu_name,
            menu_code=menu_code,
            parent_id=data.get("parent_id"),
            path=data.get("path"),
            icon=data.get("icon"),
            component=data.get("component"),
            sort_order=data.get("sort_order", 0),
            menu_level=data.get("menu_level", 1),
            permission_code=data.get("permission_code")
        )

        if success:
            return WebActionBase._success(success=True, message="创建成功", data=result.to_dict())
        return WebActionBase._fail(success=False, message=result)

    @staticmethod
    def _update_menu(data):
        """
        更新菜单
        """
        from app.services.rbac_service import rbac_service

        menu_id = data.get("id")
        if not menu_id:
            return WebActionBase._fail(success=False, message="菜单ID不能为空")

        update_fields = {}
        for field in ["menu_name", "path", "icon", "component", "sort_order",
                      "is_hidden", "status", "permission_code"]:
            if field in data:
                update_fields[field] = data[field]

        success, message = rbac_service.update_menu(menu_id, **update_fields)

        if success:
            return WebActionBase._success(success=True, message=message)
        return WebActionBase._fail(success=False, message=message)

    @staticmethod
    def _update_menu_sort(data):
        """
        批量更新菜单排序
        data: {
            "menu_orders": [
                {"id": 1, "sort_order": 0, "parent_id": null},
                {"id": 2, "sort_order": 1, "parent_id": null},
                ...
            ]
        }
        """
        from app.services.rbac_service import rbac_service

        menu_orders = data.get("menu_orders", [])
        if not menu_orders:
            return WebActionBase._fail(success=False, message="菜单排序数据不能为空")

        try:
            success_count = 0
            for item in menu_orders:
                menu_id = item.get("id")
                sort_order = item.get("sort_order")
                parent_id = item.get("parent_id")

                if menu_id is not None and sort_order is not None:
                    update_fields = {"sort_order": sort_order}
                    # 注意：parent_id 为 null 表示成为顶级菜单，也要更新
                    if "parent_id" in item:
                        update_fields["parent_id"] = parent_id

                    success, _ = rbac_service.update_menu(
                        menu_id, **update_fields)
                    if success:
                        success_count += 1

            return WebActionBase._success(success=True, message=f"成功更新 {success_count} 个菜单排序")
        except Exception as e:
            return WebActionBase._fail(success=False, message=f"更新排序失败: {str(e)}")

    @staticmethod
    def _delete_menu(data):
        """
        删除菜单
        """
        from app.services.rbac_service import rbac_service

        menu_id = data.get("id")
        if not menu_id:
            return WebActionBase._fail(success=False, message="菜单ID不能为空")

        success, message = rbac_service.delete_menu(menu_id)

        if success:
            return WebActionBase._success(success=True, message=message)
        return WebActionBase._fail(success=False, message=message)

    @staticmethod
    def _get_menu(data):
        """
        获取单个菜单信息
        """
        from app.services.rbac_service import rbac_service

        menu_id = data.get("id")
        if not menu_id:
            return WebActionBase._fail(success=False, message="菜单ID不能为空")

        menu = rbac_service.menu_repo.get_menu_by_id(menu_id)
        if menu:
            return WebActionBase._success(success=True, data=menu.to_dict())
        return WebActionBase._fail(success=False, message="菜单不存在")

    @staticmethod
    def get_user_menus():
        """
        查询用户菜单
        """
        # 需要过滤的菜单
        ignore = []
        # 获取可用菜单
        menus = current_user.get_usermenus(ignore=ignore)
        return WebActionBase._success(menus=menus, level=current_user.level)

    @staticmethod
    def get_top_menus():
        """
        查询顶底菜单列表
        """
        return WebActionBase._success(menus=current_user.get_topmenus())

    @staticmethod
    def get_users():
        """
        查询所有用户（RBAC版本）
        """
        user_list = User.get_all_users()
        Users = []
        for user in user_list:
            # 获取用户的角色列表
            roles = user.get_roles()
            # 格式化最后登录时间
            last_login = None
            if user._user and user._user.LAST_LOGIN_AT:
                last_login = user._user.LAST_LOGIN_AT.strftime(
                    '%Y-%m-%d %H:%M')

            Users.append({
                "id": user.id,
                "name": user.username,
                "username": user.username,
                "nickname": user.nickname or user.username,
                "email": user.email,
                "status": user.status,
                "roles": roles,
                "last_login_at": last_login,
                "pris": [role['role_name'] for role in roles] if roles else ["普通用户"]
            })
        return WebActionBase._success(result=Users)

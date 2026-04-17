from flask import Blueprint
from web.core.decorators import action_login_check, parse_json_data
from web.core.response import success, fail
from flask_login import current_user
from web.backend.user import User

rbac_bp = Blueprint("rbac", __name__, url_prefix="/api/web/rbac")

@rbac_bp.route('/create_menu', methods=['POST'])
@action_login_check
@parse_json_data
def _create_menu(data):
        """
        创建菜单
        """
        from app.services.rbac_service import rbac_service

        menu_name = data.get("menu_name")
        menu_code = data.get("menu_code")

        if not menu_name or not menu_code:
            return fail(success=False, message="菜单名称和代码不能为空")

        ok, result = rbac_service.create_menu(
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

        if ok:
            return success(success=True, message="创建成功", data=result.to_dict())
        return fail(success=False, message=result)

@rbac_bp.route('/create_role', methods=['POST'])
@action_login_check
@parse_json_data
def _create_role(data):
        """
        创建角色
        """
        from app.services.rbac_service import rbac_service

        role_name = data.get("role_name")
        role_code = data.get("role_code")

        if not role_name or not role_code:
            return fail(success=False, message="角色名称和代码不能为空")

        ok, result = rbac_service.create_role(
            role_name=role_name,
            role_code=role_code,
            description=data.get("description"),
            role_level=data.get("role_level", 100),
            permission_ids=data.get("permission_ids", []),
            menu_ids=data.get("menu_ids", [])
        )

        if ok:
            return success(success=True, message="创建成功", data=result.to_dict())
        return fail(success=False, message=result)

@rbac_bp.route('/create_user', methods=['POST'])
@action_login_check
@parse_json_data
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
            return fail(success=False, message="用户名和密码不能为空")

        ok, result = User.create(
            username=username,
            password=password,
            email=email,
            nickname=nickname,
            role_ids=role_ids
        )

        if ok:
            return success(success=True, message="创建成功", data=result.to_dict())
        return fail(success=False, message=result)

@rbac_bp.route('/delete_menu', methods=['POST'])
@action_login_check
@parse_json_data
def _delete_menu(data):
        """
        删除菜单
        """
        from app.services.rbac_service import rbac_service

        menu_id = data.get("id")
        if not menu_id:
            return fail(success=False, message="菜单ID不能为空")

        ok, message = rbac_service.delete_menu(menu_id)

        if ok:
            return success(success=True, message=message)
        return fail(success=False, message=message)

@rbac_bp.route('/delete_role', methods=['POST'])
@action_login_check
@parse_json_data
def _delete_role(data):
        """
        删除角色
        """
        from app.services.rbac_service import rbac_service

        role_id = data.get("id")
        if not role_id:
            return fail(success=False, message="角色ID不能为空")

        ok, message = rbac_service.delete_role(role_id)

        if ok:
            return success(success=True, message=message)
        return fail(success=False, message=message)

@rbac_bp.route('/delete_user', methods=['POST'])
@action_login_check
@parse_json_data
def _delete_user(data):
        """
        删除用户（RBAC）
        """
        from web.backend.user import User

        user_id = data.get("id")
        if not user_id:
            return fail(success=False, message="用户ID不能为空")

        ok = User.delete(user_id)

        if ok:
            return success(success=True, message="删除成功")
        return fail(success=False, message="删除失败")

@rbac_bp.route('/get_menu', methods=['POST'])
@action_login_check
@parse_json_data
def _get_menu(data):
        """
        获取单个菜单信息
        """
        from app.services.rbac_service import rbac_service

        menu_id = data.get("id")
        if not menu_id:
            return fail(success=False, message="菜单ID不能为空")

        menu = rbac_service.menu_repo.get_menu_by_id(menu_id)
        if menu:
            return success(success=True, data=menu.to_dict())
        return fail(success=False, message="菜单不存在")

@rbac_bp.route('/get_role', methods=['POST'])
@action_login_check
@parse_json_data
def _get_role(data):
        """
        获取单个角色信息
        """
        from app.services.rbac_service import rbac_service

        role_id = data.get("id")
        if not role_id:
            return fail(success=False, message="角色ID不能为空")

        role = rbac_service.get_role_by_id(role_id)
        if role:
            return success(success=True, data=role.to_dict())
        return fail(success=False, message="角色不存在")

@rbac_bp.route('/get_user', methods=['POST'])
@action_login_check
@parse_json_data
def _get_user(data):
        """
        获取单个用户信息（RBAC）
        """
        from web.backend.user import User

        user_id = data.get("id")
        if not user_id:
            return fail(success=False, message="用户ID不能为空")

        user = User.get(user_id)
        if user:
            return success(success=True, data=user.to_dict())
        return fail(success=False, message="用户不存在")

@rbac_bp.route('/reset_password', methods=['POST'])
@action_login_check
@parse_json_data
def _reset_password(data):
        """
        重置密码（RBAC）
        """
        from web.backend.user import User

        user_id = data.get("user_id")
        new_password = data.get("new_password")

        if not user_id or not new_password:
            return fail(success=False, message="用户ID和新密码不能为空")

        ok, message = User.reset_password(user_id, new_password)

        if ok:
            return success(success=True, message=message)
        return fail(success=False, message=message)

@rbac_bp.route('/update_menu', methods=['POST'])
@action_login_check
@parse_json_data
def _update_menu(data):
        """
        更新菜单
        """
        from app.services.rbac_service import rbac_service

        menu_id = data.get("id")
        if not menu_id:
            return fail(success=False, message="菜单ID不能为空")

        update_fields = {}
        for field in ["menu_name", "path", "icon", "component", "sort_order",
                      "is_hidden", "status", "permission_code"]:
            if field in data:
                update_fields[field] = data[field]

        ok, message = rbac_service.update_menu(menu_id, **update_fields)

        if ok:
            return success(success=True, message=message)
        return fail(success=False, message=message)

@rbac_bp.route('/update_menu_sort', methods=['POST'])
@action_login_check
@parse_json_data
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
            return fail(success=False, message="菜单排序数据不能为空")

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

                    ok2, _ = rbac_service.update_menu(
                        menu_id, **update_fields)
                    if ok2:
                        success_count += 1

            return success(success=True, message=f"成功更新 {success_count} 个菜单排序")
        except Exception as e:
            return fail(success=False, message=f"更新排序失败: {str(e)}")

@rbac_bp.route('/update_role', methods=['POST'])
@action_login_check
@parse_json_data
def _update_role(data):
        """
        更新角色
        """
        from app.services.rbac_service import rbac_service

        role_id = data.get("id")
        if not role_id:
            return fail(success=False, message="角色ID不能为空")

        update_fields = {}
        for field in ["role_name", "description", "role_level", "status"]:
            if field in data:
                update_fields[field] = data[field]

        ok, message = rbac_service.update_role(role_id, **update_fields)

        # 更新权限
        if "permission_ids" in data:
            rbac_service.assign_permissions_to_role(
                role_id, data["permission_ids"])

        # 更新菜单
        if "menu_ids" in data:
            rbac_service.assign_menus_to_role(role_id, data["menu_ids"])

        if ok:
            return success(success=True, message=message)
        return fail(success=False, message=message)

@rbac_bp.route('/update_user', methods=['POST'])
@action_login_check
@parse_json_data
def _update_user(data):
        """
        更新用户（RBAC）
        """
        from app.services.rbac_service import rbac_service

        user_id = data.get("id")
        if not user_id:
            return fail(success=False, message="用户ID不能为空")

        update_fields = {}
        for field in ["email", "nickname", "status", "avatar"]:
            if field in data:
                update_fields[field] = data[field]

        ok, message = rbac_service.update_user(user_id, **update_fields)

        # 更新角色
        if "role_ids" in data:
            rbac_service.assign_roles_to_user(user_id, data["role_ids"])

        if ok:
            return success(success=True, message=message)
        return fail(success=False, message=message)

def get_top_menus(data=None):
        """
        查询顶底菜单列表
        """
        return success(menus=current_user.get_topmenus())

@rbac_bp.route('/get_top_menus', methods=['POST'])
@action_login_check
@parse_json_data
def _get_top_menus(data):
        return get_top_menus(data)


def get_user_menus(data=None):
        """
        查询用户菜单
        """
        # 需要过滤的菜单
        ignore = data.get("ignore", []) if isinstance(data, dict) else []
        # 获取可用菜单
        menus = current_user.get_usermenus(ignore=ignore)
        return success(menus=menus, level=current_user.level)

@rbac_bp.route('/get_user_menus', methods=['POST'])
@action_login_check
@parse_json_data
def _get_user_menus(data):
        return get_user_menus(data)

@rbac_bp.route('/get_users', methods=['POST'])
@action_login_check
@parse_json_data
def get_users(data):
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
        return success(result=Users)


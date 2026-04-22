"""
RBAC API Blueprint
基于角色的访问控制(RBAC) RESTful API接口
"""
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from app.services.rbac_service import rbac_service, require_permission
from app.services.rbac_init import init_rbac_system, init_admin_user

rbac_bp = Blueprint('rbac', __name__, url_prefix='/api/v1/rbac')


# ==================== 认证接口 ====================

@rbac_bp.route('/auth/login', methods=['POST'])
def login():
    """
    用户登录
    
    Request Body:
        - username: 用户名
        - password: 密码
    
    Returns:
        - token: 访问令牌
        - user: 用户信息
    """
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({"code": 400, "success": False, "message": "用户名和密码不能为空"})
    
    # 获取客户端信息
    login_ip = request.remote_addr
    user_agent = request.headers.get('User-Agent', '')
    
    success, result = rbac_service.authenticate_user(
        username, password, login_ip, user_agent
    )
    
    if not success:
        return jsonify({"code": 401, "success": False, "message": result})
    
    user = result
    
    # 生成访问令牌
    from web.security import generate_access_token
    from app.utils import TokenCache
    
    token = generate_access_token(user.USERNAME)
    TokenCache.set(user.USERNAME, token)
    
    return jsonify({
        "code": 0,
        "success": True,
        "message": "登录成功",
        "data": {
            "token": token,
            "user": user.to_dict()
        }
    })


@rbac_bp.route('/auth/logout', methods=['POST'])
@login_required
def logout():
    """
    用户登出
    """
    from app.utils import TokenCache
    
    # 清除token缓存
    token = request.headers.get('Authorization')
    if token:
        TokenCache.delete(token)
    
    return jsonify({
        "code": 0,
        "success": True,
        "message": "登出成功"
    })


@rbac_bp.route('/auth/change-password', methods=['POST'])
@login_required
def change_password():
    """
    修改密码
    
    Request Body:
        - old_password: 旧密码
        - new_password: 新密码
    """
    data = request.get_json()
    old_password = data.get('old_password')
    new_password = data.get('new_password')
    
    if not old_password or not new_password:
        return jsonify({"code": 400, "success": False, "message": "密码不能为空"})
    
    user_id = current_user.get_id()
    success, message = rbac_service.change_password(user_id, old_password, new_password)
    
    if success:
        return jsonify({"code": 0, "success": True, "message": message})
    return jsonify({"code": 400, "success": False, "message": message})


# ==================== 用户管理接口 ====================

@rbac_bp.route('/users', methods=['GET'])
@login_required
@require_permission('user:view')
def get_users():
    """
    获取用户列表
    
    Query Parameters:
        - page: 页码 (默认1)
        - page_size: 每页数量 (默认20)
    """
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)
    
    users, total = rbac_service.get_users(page=page, page_size=page_size)
    
    return jsonify({
        "code": 0,
        "success": True,
        "data": {
            "list": [user.to_dict() for user in users],
            "total": total,
            "page": page,
            "page_size": page_size
        }
    })


@rbac_bp.route('/users/<int:user_id>', methods=['GET'])
@login_required
@require_permission('user:view')
def get_user(user_id):
    """
    获取单个用户信息
    """
    user = rbac_service.get_user_by_id(user_id)
    if not user:
        return jsonify({"code": 404, "success": False, "message": "用户不存在"})
    
    return jsonify({
        "code": 0,
        "success": True,
        "data": user.to_dict()
    })


@rbac_bp.route('/users', methods=['POST'])
@login_required
@require_permission('user:create')
def create_user():
    """
    创建用户
    
    Request Body:
        - username: 用户名 (必需)
        - password: 密码 (必需)
        - email: 邮箱 (可选)
        - nickname: 昵称 (可选)
        - role_ids: 角色ID列表 (可选)
    """
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({"code": 400, "success": False, "message": "用户名和密码不能为空"})
    
    success, result = rbac_service.create_user(
        username=username,
        password=password,
        email=data.get('email'),
        nickname=data.get('nickname'),
        role_ids=data.get('role_ids', [])
    )
    
    if success:
        return jsonify({"code": 0, "success": True, "message": "创建成功", "data": result.to_dict()})
    return jsonify({"code": 400, "success": False, "message": result})


@rbac_bp.route('/users/<int:user_id>', methods=['PUT'])
@login_required
@require_permission('user:update')
def update_user(user_id):
    """
    更新用户信息
    
    Request Body:
        - email: 邮箱
        - nickname: 昵称
        - status: 状态 (1=启用, 0=禁用)
        - role_ids: 角色ID列表
    """
    data = request.get_json()
    
    # 过滤允许更新的字段
    update_fields = {}
    for field in ['email', 'nickname', 'status', 'avatar']:
        if field in data:
            update_fields[field] = data[field]
    
    success, message = rbac_service.update_user(user_id, **update_fields)
    
    # 如果提供了角色ID，更新角色
    if 'role_ids' in data:
        rbac_service.assign_roles_to_user(user_id, data['role_ids'])
    
    if success:
        return jsonify({"code": 0, "success": True, "message": message})
    return jsonify({"code": 400, "success": False, "message": message})


@rbac_bp.route('/users/<int:user_id>', methods=['DELETE'])
@login_required
@require_permission('user:delete')
def delete_user(user_id):
    """
    删除用户
    """
    # 不能删除自己
    if user_id == current_user.get_id():
        return jsonify({"code": 400, "success": False, "message": "不能删除当前登录用户"})
    
    success, message = rbac_service.delete_user(user_id)
    
    if success:
        return jsonify({"code": 0, "success": True, "message": message})
    return jsonify({"code": 400, "success": False, "message": message})


@rbac_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
@require_permission('user:update')
def reset_user_password(user_id):
    """
    重置用户密码（管理员功能）
    
    Request Body:
        - new_password: 新密码
    """
    data = request.get_json()
    new_password = data.get('new_password')
    
    if not new_password:
        return jsonify({"code": 400, "success": False, "message": "新密码不能为空"})
    
    success, message = rbac_service.reset_password(user_id, new_password)
    
    if success:
        return jsonify({"code": 0, "success": True, "message": message})
    return jsonify({"code": 400, "success": False, "message": message})


@rbac_bp.route('/users/<int:user_id>/permissions', methods=['GET'])
@login_required
def get_user_permissions(user_id):
    """
    获取用户的权限列表
    """
    # 只能查看自己的权限，除非有用户管理权限
    if user_id != current_user.get_id():
        if not rbac_service.check_permission(current_user.get_id(), 'user:view'):
            return jsonify({"code": 403, "success": False, "message": "无权查看其他用户的权限"})
    
    permissions = rbac_service.get_user_permissions(user_id)
    
    return jsonify({
        "code": 0,
        "success": True,
        "data": {
            "permissions": list(permissions)
        }
    })


# ==================== 角色管理接口 ====================

@rbac_bp.route('/roles', methods=['GET'])
@login_required
@require_permission('role:view')
def get_roles():
    """
    获取角色列表
    """
    roles = rbac_service.get_all_roles()
    
    return jsonify({
        "code": 0,
        "success": True,
        "data": [role.to_dict() for role in roles]
    })


@rbac_bp.route('/roles/<int:role_id>', methods=['GET'])
@login_required
@require_permission('role:view')
def get_role(role_id):
    """
    获取单个角色信息
    """
    role = rbac_service.get_role_by_id(role_id)
    if not role:
        return jsonify({"code": 404, "success": False, "message": "角色不存在"})
    
    return jsonify({
        "code": 0,
        "success": True,
        "data": role.to_dict()
    })


@rbac_bp.route('/roles', methods=['POST'])
@login_required
@require_permission('role:create')
def create_role():
    """
    创建角色
    
    Request Body:
        - role_name: 角色名称 (必需)
        - role_code: 角色代码 (必需)
        - description: 描述 (可选)
        - role_level: 角色级别 (可选)
        - permission_ids: 权限ID列表 (可选)
        - menu_ids: 菜单ID列表 (可选)
    """
    data = request.get_json()
    role_name = data.get('role_name')
    role_code = data.get('role_code')
    
    if not role_name or not role_code:
        return jsonify({"code": 400, "success": False, "message": "角色名称和代码不能为空"})
    
    success, result = rbac_service.create_role(
        role_name=role_name,
        role_code=role_code,
        description=data.get('description'),
        role_level=data.get('role_level', 100),
        permission_ids=data.get('permission_ids', []),
        menu_ids=data.get('menu_ids', [])
    )
    
    if success:
        return jsonify({"code": 0, "success": True, "message": "创建成功", "data": result.to_dict()})
    return jsonify({"code": 400, "success": False, "message": result})


@rbac_bp.route('/roles/<int:role_id>', methods=['PUT'])
@login_required
@require_permission('role:update')
def update_role(role_id):
    """
    更新角色信息
    """
    data = request.get_json()
    
    update_fields = {}
    for field in ['role_name', 'description', 'role_level', 'status']:
        if field in data:
            update_fields[field] = data[field]
    
    success, message = rbac_service.update_role(role_id, **update_fields)
    
    # 更新权限
    if 'permission_ids' in data:
        rbac_service.assign_permissions_to_role(role_id, data['permission_ids'])
    
    # 更新菜单
    if 'menu_ids' in data:
        rbac_service.assign_menus_to_role(role_id, data['menu_ids'])
    
    if success:
        return jsonify({"code": 0, "success": True, "message": message})
    return jsonify({"code": 400, "success": False, "message": message})


@rbac_bp.route('/roles/<int:role_id>', methods=['DELETE'])
@login_required
@require_permission('role:delete')
def delete_role(role_id):
    """
    删除角色
    """
    success, message = rbac_service.delete_role(role_id)
    
    if success:
        return jsonify({"code": 0, "success": True, "message": message})
    return jsonify({"code": 400, "success": False, "message": message})


# ==================== 权限管理接口 ====================

@rbac_bp.route('/permissions', methods=['GET'])
@login_required
@require_permission('permission:view')
def get_permissions():
    """
    获取权限列表
    
    Query Parameters:
        - module: 模块筛选
    """
    module = request.args.get('module')
    permissions = rbac_service.get_all_permissions(module=module)
    
    return jsonify({
        "code": 0,
        "success": True,
        "data": [perm.to_dict() for perm in permissions]
    })


@rbac_bp.route('/permissions', methods=['POST'])
@login_required
@require_permission('permission:create')
def create_permission():
    """
    创建权限
    
    Request Body:
        - permission_name: 权限名称 (必需)
        - permission_code: 权限代码 (必需)
        - permission_type: 权限类型 (可选)
        - module: 所属模块 (可选)
        - description: 描述 (可选)
    """
    data = request.get_json()
    permission_name = data.get('permission_name')
    permission_code = data.get('permission_code')
    
    if not permission_name or not permission_code:
        return jsonify({"code": 400, "success": False, "message": "权限名称和代码不能为空"})
    
    success, result = rbac_service.create_permission(
        permission_name=permission_name,
        permission_code=permission_code,
        permission_type=data.get('permission_type', 'api'),
        module=data.get('module'),
        description=data.get('description')
    )
    
    if success:
        return jsonify({"code": 0, "success": True, "message": "创建成功", "data": result.to_dict()})
    return jsonify({"code": 400, "success": False, "message": result})


@rbac_bp.route('/permissions/<int:permission_id>', methods=['PUT'])
@login_required
@require_permission('permission:update')
def update_permission(permission_id):
    """
    更新权限
    """
    data = request.get_json()
    
    update_fields = {}
    for field in ['permission_name', 'description', 'status', 'module']:
        if field in data:
            update_fields[field] = data[field]
    
    success, message = rbac_service.update_permission(permission_id, **update_fields)
    
    if success:
        return jsonify({"code": 0, "success": True, "message": message})
    return jsonify({"code": 400, "success": False, "message": message})


@rbac_bp.route('/permissions/<int:permission_id>', methods=['DELETE'])
@login_required
@require_permission('permission:delete')
def delete_permission(permission_id):
    """
    删除权限
    """
    success, message = rbac_service.delete_permission(permission_id)
    
    if success:
        return jsonify({"code": 0, "success": True, "message": message})
    return jsonify({"code": 400, "success": False, "message": message})


# ==================== 菜单管理接口 ====================

@rbac_bp.route('/menus', methods=['GET'])
@login_required
def get_menus():
    """
    获取菜单列表
    
    Query Parameters:
        - tree: 是否返回树形结构 (1=是, 0=否)
    """
    tree = request.args.get('tree', '1') == '1'
    
    if tree:
        menus = rbac_service.get_menu_tree()
    else:
        menus = [m.to_dict() for m in rbac_service.menu_repo.get_all_menus(status=1)]
    
    return jsonify({
        "code": 0,
        "success": True,
        "data": menus
    })


@rbac_bp.route('/menus/tree', methods=['GET'])
@login_required
def get_menu_tree():
    """
    获取菜单树形结构
    """
    menus = rbac_service.get_menu_tree()
    
    return jsonify({
        "code": 0,
        "success": True,
        "data": menus
    })


@rbac_bp.route('/menus/user', methods=['GET'])
@login_required
def get_user_menus():
    """
    获取当前用户的菜单
    """
    user_id = current_user.get_id()
    menus = rbac_service.get_user_menus(user_id)
    
    return jsonify({
        "code": 0,
        "success": True,
        "data": [menu.to_dict() for menu in menus]
    })


@rbac_bp.route('/menus', methods=['POST'])
@login_required
@require_permission('menu:create')
def create_menu():
    """
    创建菜单
    
    Request Body:
        - menu_name: 菜单名称 (必需)
        - menu_code: 菜单代码 (必需)
        - parent_id: 父菜单ID (可选)
        - path: 路由路径 (可选)
        - icon: 图标 (可选)
        - sort_order: 排序号 (可选)
        - permission_code: 关联权限代码 (可选)
    """
    data = request.get_json()
    menu_name = data.get('menu_name')
    menu_code = data.get('menu_code')
    
    if not menu_name or not menu_code:
        return jsonify({"code": 400, "success": False, "message": "菜单名称和代码不能为空"})
    
    success, result = rbac_service.create_menu(
        menu_name=menu_name,
        menu_code=menu_code,
        parent_id=data.get('parent_id'),
        path=data.get('path'),
        icon=data.get('icon'),
        sort_order=data.get('sort_order', 0),
        menu_level=data.get('menu_level', 1),
        permission_code=data.get('permission_code')
    )
    
    if success:
        return jsonify({"code": 0, "success": True, "message": "创建成功", "data": result.to_dict()})
    return jsonify({"code": 400, "success": False, "message": result})


@rbac_bp.route('/menus/<int:menu_id>', methods=['PUT'])
@login_required
@require_permission('menu:update')
def update_menu(menu_id):
    """
    更新菜单
    """
    data = request.get_json()
    
    update_fields = {}
    for field in ['menu_name', 'path', 'icon', 'sort_order', 'is_hidden', 'status', 'permission_code']:
        if field in data:
            update_fields[field] = data[field]
    
    success, message = rbac_service.update_menu(menu_id, **update_fields)
    
    if success:
        return jsonify({"code": 0, "success": True, "message": message})
    return jsonify({"code": 400, "success": False, "message": message})


@rbac_bp.route('/menus/<int:menu_id>', methods=['DELETE'])
@login_required
@require_permission('menu:delete')
def delete_menu(menu_id):
    """
    删除菜单
    """
    success, message = rbac_service.delete_menu(menu_id)
    
    if success:
        return jsonify({"code": 0, "success": True, "message": message})
    return jsonify({"code": 400, "success": False, "message": message})


# ==================== 系统初始化接口 ====================

@rbac_bp.route('/system/init', methods=['POST'])
def init_system():
    """
    初始化RBAC系统（创建默认权限、菜单、角色）
    
    Request Body:
        - admin_username: 管理员用户名
        - admin_password: 管理员密码
    """
    data = request.get_json()
    admin_username = data.get('admin_username')
    admin_password = data.get('admin_password')
    
    # 初始化RBAC系统
    success = init_rbac_system()
    
    if success and admin_username and admin_password:
        # 创建管理员用户
        init_admin_user(admin_username, admin_password)
    
    if success:
        return jsonify({
            "code": 0,
            "success": True,
            "message": "RBAC系统初始化成功"
        })
    return jsonify({
        "code": 500,
        "success": False,
        "message": "RBAC系统初始化失败"
    })


# ==================== 当前用户信息接口 ====================

@rbac_bp.route('/me', methods=['GET'])
@login_required
def get_current_user():
    """
    获取当前登录用户信息
    """
    user = rbac_service.get_user_by_id(current_user.get_id())
    if not user:
        return jsonify({"code": 404, "success": False, "message": "用户不存在"})
    
    # 获取用户权限
    permissions = rbac_service.get_user_permissions(user.ID)
    
    return jsonify({
        "code": 0,
        "success": True,
        "data": {
            **user.to_dict(),
            "permissions": list(permissions)
        }
    })

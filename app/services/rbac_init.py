"""
RBAC初始化模块
用于初始化RBAC系统的默认数据：角色、权限、菜单
"""
from app.services.rbac_service import rbac_service
from app.db.repositories import (
    RBACRoleRepository,
    RBACPermissionRepository,
    RBACMenuRepository,
    RBACUserRepository
)
from app.db.models.rbac import RBACUser
import log


# 默认权限定义
DEFAULT_PERMISSIONS = [
    # 用户管理权限
    {"name": "用户查看", "code": "user:view", "type": "api", "module": "user"},
    {"name": "用户创建", "code": "user:create", "type": "api", "module": "user"},
    {"name": "用户编辑", "code": "user:update", "type": "api", "module": "user"},
    {"name": "用户删除", "code": "user:delete", "type": "api", "module": "user"},
    
    # 角色管理权限
    {"name": "角色查看", "code": "role:view", "type": "api", "module": "role"},
    {"name": "角色创建", "code": "role:create", "type": "api", "module": "role"},
    {"name": "角色编辑", "code": "role:update", "type": "api", "module": "role"},
    {"name": "角色删除", "code": "role:delete", "type": "api", "module": "role"},
    
    # 权限管理权限
    {"name": "权限查看", "code": "permission:view", "type": "api", "module": "permission"},
    {"name": "权限创建", "code": "permission:create", "type": "api", "module": "permission"},
    {"name": "权限编辑", "code": "permission:update", "type": "api", "module": "permission"},
    {"name": "权限删除", "code": "permission:delete", "type": "api", "module": "permission"},
    
    # 菜单管理权限
    {"name": "菜单查看", "code": "menu:view", "type": "api", "module": "menu"},
    {"name": "菜单创建", "code": "menu:create", "type": "api", "module": "menu"},
    {"name": "菜单编辑", "code": "menu:update", "type": "api", "module": "menu"},
    {"name": "菜单删除", "code": "menu:delete", "type": "api", "module": "menu"},
    
    # 系统设置权限
    {"name": "系统设置查看", "code": "setting:view", "type": "api", "module": "setting"},
    {"name": "系统设置编辑", "code": "setting:update", "type": "api", "module": "setting"},
    
    # 媒体库权限
    {"name": "媒体库查看", "code": "library:view", "type": "menu", "module": "library"},
    {"name": "媒体库管理", "code": "library:manage", "type": "api", "module": "library"},
    
    # 站点管理权限
    {"name": "站点查看", "code": "site:view", "type": "menu", "module": "site"},
    {"name": "站点管理", "code": "site:manage", "type": "api", "module": "site"},
    
    # 下载管理权限
    {"name": "下载查看", "code": "download:view", "type": "menu", "module": "download"},
    {"name": "下载管理", "code": "download:manage", "type": "api", "module": "download"},
    
    # 订阅管理权限
    {"name": "订阅查看", "code": "rss:view", "type": "menu", "module": "rss"},
    {"name": "订阅管理", "code": "rss:manage", "type": "api", "module": "rss"},
    
    # 搜索权限
    {"name": "资源搜索", "code": "search:view", "type": "menu", "module": "search"},
    {"name": "执行搜索", "code": "search:execute", "type": "api", "module": "search"},
    
    # 服务权限
    {"name": "服务查看", "code": "service:view", "type": "menu", "module": "service"},
    {"name": "服务管理", "code": "service:manage", "type": "api", "module": "service"},
    
    # 插件权限
    {"name": "插件查看", "code": "plugin:view", "type": "menu", "module": "plugin"},
    {"name": "插件管理", "code": "plugin:manage", "type": "api", "module": "plugin"},
    
    # 日志权限
    {"name": "日志查看", "code": "log:view", "type": "menu", "module": "log"},
]


# 默认菜单定义（使用 Lucide 图标名称）
DEFAULT_MENUS = [
    {
        "name": "我的媒体库",
        "code": "media_library",
        "path": "/",
        "icon": "home",
        "sort_order": 1,
        "level": 1,
        "permission_code": "library:view"
    },
    {
        "name": "资源搜索",
        "code": "search",
        "path": "/search",
        "icon": "search",
        "sort_order": 2,
        "level": 1,
        "permission_code": "search:view"
    },
    {
        "name": "站点管理",
        "code": "site",
        "icon": "server",
        "sort_order": 3,
        "level": 1,
        "children": [
            {"name": "站点维护", "code": "site_maintenance", "path": "/site", "icon": "server", "sort_order": 1, "level": 2, "permission_code": "site:view"},
            {"name": "数据统计", "code": "site_statistics", "path": "/statistics", "icon": "pie-chart", "sort_order": 2, "level": 2, "permission_code": "site:view"},
            {"name": "刷流任务", "code": "brush_task", "path": "/brushtask", "icon": "list-check", "sort_order": 3, "level": 2, "permission_code": "site:manage"},
        ]
    },
    {
        "name": "订阅管理",
        "code": "rss",
        "icon": "rss",
        "sort_order": 4,
        "level": 1,
        "children": [
            {"name": "电影订阅", "code": "movie_rss", "path": "/movie_rss", "icon": "film", "sort_order": 1, "level": 2, "permission_code": "rss:view"},
            {"name": "电视剧订阅", "code": "tv_rss", "path": "/tv_rss", "icon": "tv", "sort_order": 2, "level": 2, "permission_code": "rss:view"},
            {"name": "自定义订阅", "code": "custom_rss", "path": "/user_rss", "icon": "file-text", "sort_order": 3, "level": 2, "permission_code": "rss:manage"},
        ]
    },
    {
        "name": "下载管理",
        "code": "download",
        "icon": "download",
        "sort_order": 5,
        "level": 1,
        "children": [
            {"name": "正在下载", "code": "downloading", "path": "/downloading", "icon": "loader-2", "sort_order": 1, "level": 2, "permission_code": "download:view"},
            {"name": "近期下载", "code": "downloaded", "path": "/downloaded", "icon": "download", "sort_order": 2, "level": 2, "permission_code": "download:view"},
            {"name": "自动删种", "code": "torrent_remove", "path": "/torrent_remove", "icon": "trash-2", "sort_order": 3, "level": 2, "permission_code": "download:manage"},
        ]
    },
    {
        "name": "媒体整理",
        "code": "media",
        "icon": "file-pen",
        "sort_order": 6,
        "level": 1,
        "children": [
            {"name": "文件管理", "code": "file_manager", "path": "/mediafile", "icon": "folder-open", "sort_order": 1, "level": 2, "permission_code": "library:manage"},
            {"name": "手动识别", "code": "manual_identify", "path": "/unidentification", "icon": "scan-line", "sort_order": 2, "level": 2, "permission_code": "library:manage"},
            {"name": "历史记录", "code": "history", "path": "/history", "icon": "history", "sort_order": 3, "level": 2, "permission_code": "library:view"},
        ]
    },
    {
        "name": "服务",
        "code": "service",
        "path": "/service",
        "icon": "layout-dashboard",
        "sort_order": 7,
        "level": 1,
        "permission_code": "service:view"
    },
    {
        "name": "系统设置",
        "code": "setting",
        "icon": "settings",
        "sort_order": 8,
        "level": 1,
        "children": [
            {"name": "基础设置", "code": "basic_setting", "path": "/basic", "icon": "sliders", "sort_order": 1, "level": 2, "permission_code": "setting:view"},
            {"name": "媒体库设置", "code": "library_setting", "path": "/library", "icon": "tv", "sort_order": 2, "level": 2, "permission_code": "setting:view"},
            {"name": "目录同步", "code": "directory_sync", "path": "/directorysync", "icon": "refresh-cw", "sort_order": 3, "level": 2, "permission_code": "setting:view"},
            {"name": "下载器设置", "code": "downloader_setting", "path": "/downloader", "icon": "download", "sort_order": 4, "level": 2, "permission_code": "setting:view"},
            {"name": "索引器设置", "code": "indexer_setting", "path": "/indexer", "icon": "search", "sort_order": 6, "level": 2, "permission_code": "setting:view"},
            {"name": "媒体服务器", "code": "media_server", "path": "/mediaserver", "icon": "server", "sort_order": 8, "level": 2, "permission_code": "setting:view"},
            {"name": "通知设置", "code": "notification_setting", "path": "/notification", "icon": "bell", "sort_order": 9, "level": 2, "permission_code": "setting:view"},
            {"name": "自定义识别词", "code": "custom_words", "path": "/customwords", "icon": "file-code", "sort_order": 10, "level": 2, "permission_code": "setting:view"},
            {"name": "过滤规则", "code": "filter_rule", "path": "/filterrule", "icon": "filter", "sort_order": 11, "level": 2, "permission_code": "setting:view"},
            {"name": "插件管理", "code": "plugin_management", "path": "/plugin", "icon": "puzzle", "sort_order": 13, "level": 2, "permission_code": "plugin:view"},
            {"name": "用户管理", "code": "user_management", "path": "/users", "icon": "users", "sort_order": 14, "level": 2, "permission_code": "user:view"},
            {"name": "角色管理", "code": "role_management", "path": "/roles", "icon": "shield", "sort_order": 15, "level": 2, "permission_code": "role:view"},
            {"name": "菜单管理", "code": "menu_management", "path": "/menus", "icon": "menu-square", "sort_order": 16, "level": 2, "permission_code": "menu:view"},
        ]
    },
]


# 默认角色定义
DEFAULT_ROLES = [
    {
        "name": "超级管理员",
        "code": "superadmin",
        "description": "拥有系统所有权限",
        "level": 1,
        "permissions": [],  # 超级管理员拥有所有权限，无需指定
        "menus": []  # 超级管理员可以访问所有菜单
    },
    {
        "name": "管理员",
        "code": "admin",
        "description": "拥有大部分管理权限",
        "level": 10,
        "permissions": [
            "user:view", "user:create", "user:update",
            "role:view",
            "permission:view",
            "menu:view",
            "setting:view", "setting:update",
            "library:view", "library:manage",
            "site:view", "site:manage",
            "download:view", "download:manage",
            "rss:view", "rss:manage",
            "search:view", "search:execute",
            "service:view", "service:manage",
            "plugin:view", "plugin:manage",
            "log:view",
        ],
        "menus": [
            "media_library", "search", "site", "site_maintenance", "site_statistics", "brush_task",
            "rss", "movie_rss", "tv_rss", "custom_rss",
            "download", "downloading", "downloaded", "torrent_remove",
            "media", "file_manager", "manual_identify", "history",
            "service", "setting", "basic_setting", "user_management", "library_setting", "plugin_management"
        ]
    },
    {
        "name": "普通用户",
        "code": "user",
        "description": "拥有基本使用权限",
        "level": 100,
        "permissions": [
            "library:view",
            "site:view",
            "download:view",
            "rss:view",
            "search:view", "search:execute",
            "service:view",
        ],
        "menus": [
            "media_library", "search",
            "site", "site_maintenance", "site_statistics",
            "rss", "movie_rss", "tv_rss",
            "download", "downloading", "downloaded",
            "media", "history",
            "service",
        ]
    },
    {
        "name": "访客",
        "code": "guest",
        "description": "仅拥有查看权限",
        "level": 200,
        "permissions": [
            "library:view",
            "search:view",
        ],
        "menus": [
            "media_library", "search",
        ]
    },
]


def init_rbac_permissions():
    """初始化权限数据"""
    permission_repo = RBACPermissionRepository()
    created_count = 0
    
    for perm_data in DEFAULT_PERMISSIONS:
        existing = permission_repo.get_permission_by_code(perm_data["code"])
        if not existing:
            permission_repo.create_permission(
                permission_name=perm_data["name"],
                permission_code=perm_data["code"],
                permission_type=perm_data["type"],
                module=perm_data["module"]
            )
            created_count += 1
            log.info(f"【RBAC初始化】创建权限: {perm_data['name']}")
    
    log.info(f"【RBAC初始化】权限初始化完成，新增 {created_count} 个权限")
    return created_count


def init_rbac_menus():
    """初始化菜单数据"""
    menu_repo = RBACMenuRepository()
    created_count = 0
    
    def create_menu_recursive(menu_data, parent_id=None):
        nonlocal created_count
        
        existing = menu_repo.get_menu_by_code(menu_data["code"])
        if not existing:
            # 创建菜单，处理装饰器可能返回bool的情况
            result = menu_repo.create_menu(
                menu_name=menu_data["name"],
                menu_code=menu_data["code"],
                parent_id=parent_id,
                path=menu_data.get("path"),
                icon=menu_data.get("icon"),
                sort_order=menu_data.get("sort_order", 0),
                menu_level=menu_data.get("level", 1),
                permission_code=menu_data.get("permission_code")
            )
            # 如果装饰器返回bool，重新查询菜单
            if isinstance(result, bool):
                menu = menu_repo.get_menu_by_code(menu_data["code"])
            else:
                menu = result
            
            if menu:
                created_count += 1
                log.info(f"【RBAC初始化】创建菜单: {menu_data['name']}")
                menu_id = menu.ID
            else:
                log.error(f"【RBAC初始化】创建菜单失败: {menu_data['name']}")
                return
        else:
            menu_id = existing.ID
        
        # 递归创建子菜单
        if "children" in menu_data:
            for child_data in menu_data["children"]:
                create_menu_recursive(child_data, menu_id)
    
    for menu_data in DEFAULT_MENUS:
        create_menu_recursive(menu_data)
    
    log.info(f"【RBAC初始化】菜单初始化完成，新增 {created_count} 个菜单")
    return created_count


def init_rbac_roles():
    """初始化角色数据"""
    role_repo = RBACRoleRepository()
    permission_repo = RBACPermissionRepository()
    menu_repo = RBACMenuRepository()
    created_count = 0
    
    for role_data in DEFAULT_ROLES:
        existing = role_repo.get_role_by_code(role_data["code"])
        if not existing:
            role = role_repo.create_role(
                role_name=role_data["name"],
                role_code=role_data["code"],
                description=role_data["description"],
                role_level=role_data["level"]
            )
            created_count += 1
            log.info(f"【RBAC初始化】创建角色: {role_data['name']}")
            
            # 为角色分配权限
            if role_data["permissions"]:
                permissions = permission_repo.get_permissions_by_codes(role_data["permissions"])
                permission_ids = [p.ID for p in permissions]
                if permission_ids:
                    role_repo.assign_permissions_to_role(role.ID, permission_ids)
                    log.info(f"【RBAC初始化】为角色 {role_data['name']} 分配 {len(permission_ids)} 个权限")
            
            # 为角色分配菜单
            if role_data["menus"]:
                menu_ids = []
                for menu_code in role_data["menus"]:
                    menu = menu_repo.get_menu_by_code(menu_code)
                    if menu:
                        menu_ids.append(menu.ID)
                if menu_ids:
                    role_repo.assign_menus_to_role(role.ID, menu_ids)
                    log.info(f"【RBAC初始化】为角色 {role_data['name']} 分配 {len(menu_ids)} 个菜单")
    
    log.info(f"【RBAC初始化】角色初始化完成，新增 {created_count} 个角色")
    return created_count


def init_rbac_system():
    """
    初始化RBAC系统
    创建默认的权限、菜单、角色
    """
    try:
        log.info("【RBAC初始化】开始初始化RBAC系统...")
        
        # 1. 初始化权限
        init_rbac_permissions()
        
        # 2. 初始化菜单
        init_rbac_menus()
        
        # 3. 初始化角色
        init_rbac_roles()
        
        log.info("【RBAC初始化】RBAC系统初始化完成")
        return True
    except Exception as e:
        log.error(f"【RBAC初始化】初始化失败: {str(e)}")
        return False


def init_admin_user(admin_username: str, admin_password: str):
    """
    初始化管理员用户
    
    Args:
        admin_username: 管理员用户名
        admin_password: 管理员密码
    """
    try:
        user_repo = RBACUserRepository()
        role_repo = RBACRoleRepository()
        
        # 检查是否已存在该用户
        existing = user_repo.get_user_by_username(admin_username)
        if existing:
            log.info(f"【RBAC初始化】管理员用户 {admin_username} 已存在")
            return True
        
        # 创建管理员用户
        from werkzeug.security import generate_password_hash
        password_hash = generate_password_hash(admin_password)
        
        user = user_repo.create_user(
            username=admin_username,
            password_hash=password_hash,
            nickname="系统管理员",
            is_superadmin=1
        )
        
        # 分配超级管理员角色
        superadmin_role = role_repo.get_role_by_code("superadmin")
        if superadmin_role:
            user_repo.assign_roles_to_user(user.ID, [superadmin_role.ID])
        
        log.info(f"【RBAC初始化】创建管理员用户: {admin_username}")
        return True
    except Exception as e:
        log.error(f"【RBAC初始化】创建管理员用户失败: {str(e)}")
        return False

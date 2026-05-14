"""
RBAC初始化模块
用于初始化RBAC系统的默认数据：角色、权限、菜单
"""

import log
from app.db.repositories.rbac_repo_adapter import (
    RBACMenuRepositoryAdapter,
    RBACPermissionRepositoryAdapter,
    RBACRoleRepositoryAdapter,
    RBACUserRepositoryAdapter,
)

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
    # 探索权限
    {"name": "探索查看", "code": "discovery:view", "type": "menu", "module": "discovery"},
    {"name": "探索管理", "code": "discovery:manage", "type": "api", "module": "discovery"},
    # 服务权限
    {"name": "服务查看", "code": "service:view", "type": "menu", "module": "service"},
    {"name": "服务管理", "code": "service:manage", "type": "api", "module": "service"},
    # 插件权限
    {"name": "插件查看", "code": "plugin:view", "type": "menu", "module": "plugin"},
    {"name": "插件管理", "code": "plugin:manage", "type": "api", "module": "plugin"},
    # 日志权限
    {"name": "日志查看", "code": "log:view", "type": "menu", "module": "log"},
    # API Key 权限
    {"name": "API Key 查看", "code": "apikey:view", "type": "menu", "module": "apikey"},
    {"name": "API Key 创建", "code": "apikey:create", "type": "api", "module": "apikey"},
    {"name": "API Key 编辑", "code": "apikey:update", "type": "api", "module": "apikey"},
    {"name": "API Key 删除", "code": "apikey:delete", "type": "api", "module": "apikey"},
]


# 默认菜单定义（code = 前端路由 name，component = Vben 格式路径）
DEFAULT_MENUS = [
    {
        "name": "首页",
        "code": "Home",
        "path": "/dashboard/home",
        "icon": "lucide:layout-dashboard",
        "component": "/dashboard/home/index",
        "sort_order": 0,
        "level": 1,
        "permission_code": "",
    },
    {
        "name": "我的媒体库",
        "code": "Library",
        "path": "/library",
        "icon": "lucide:tv",
        "component": "/media/library/index",
        "sort_order": 1,
        "level": 1,
        "permission_code": "library:view",
    },
    {
        "name": "资源搜索",
        "code": "MediaSearch",
        "path": "/media/search",
        "icon": "lucide:search",
        "component": "/media/search/index",
        "sort_order": 2,
        "level": 1,
        "permission_code": "search:view",
    },
    {
        "name": "探索",
        "code": "Discovery",
        "path": "",
        "icon": "lucide:compass",
        "sort_order": 3,
        "level": 1,
        "permission_code": "discovery:view",
        "children": [
            {
                "name": "排行榜",
                "code": "Ranking",
                "path": "/discovery/ranking",
                "icon": "lucide:trophy",
                "component": "/media/discovery/index",
                "sort_order": 1,
                "level": 2,
                "permission_code": "discovery:view",
            },
            {
                "name": "豆瓣电影",
                "code": "DoubanMovie",
                "path": "/discovery/douban-movie",
                "icon": "lucide:film",
                "component": "/media/discovery/index",
                "sort_order": 2,
                "level": 2,
                "permission_code": "discovery:view",
            },
            {
                "name": "豆瓣电视剧",
                "code": "DoubanTv",
                "path": "/discovery/douban-tv",
                "icon": "lucide:tv",
                "component": "/media/discovery/index",
                "sort_order": 3,
                "level": 2,
                "permission_code": "discovery:view",
            },
            {
                "name": "TMDB电影",
                "code": "TmdbMovie",
                "path": "/discovery/tmdb-movie",
                "icon": "lucide:clapperboard",
                "component": "/media/discovery/index",
                "sort_order": 4,
                "level": 2,
                "permission_code": "discovery:view",
            },
            {
                "name": "TMDB电视剧",
                "code": "TmdbTv",
                "path": "/discovery/tmdb-tv",
                "icon": "lucide:monitor-play",
                "component": "/media/discovery/index",
                "sort_order": 5,
                "level": 2,
                "permission_code": "discovery:view",
            },
            {
                "name": "Bangumi",
                "code": "Bangumi",
                "path": "/discovery/bangumi",
                "icon": "lucide:calendar-days",
                "component": "/media/discovery/index",
                "sort_order": 6,
                "level": 2,
                "permission_code": "discovery:view",
            },
            {
                "name": "更多推荐",
                "code": "DiscoveryRecommend",
                "path": "/discovery/recommend",
                "icon": "lucide:more-horizontal",
                "component": "/media/discovery/recommend",
                "sort_order": 7,
                "level": 2,
                "permission_code": "discovery:view",
                "hide_in_menu": 1,
            },
        ],
    },
    {
        "name": "媒体详情",
        "code": "MediaDetail",
        "path": "/media/detail",
        "icon": "lucide:info",
        "component": "/media/detail/index",
        "sort_order": 999,
        "level": 1,
        "permission_code": "library:view",
        "hide_in_menu": 1,
    },
    {
        "name": "站点管理",
        "code": "Site",
        "path": "",
        "icon": "lucide:server",
        "sort_order": 4,
        "level": 1,
        "permission_code": "site:view",
        "children": [
            {
                "name": "站点维护",
                "code": "SiteMaintenance",
                "path": "/site/list",
                "icon": "lucide:server",
                "component": "/site/list/index",
                "sort_order": 1,
                "level": 2,
                "permission_code": "site:view",
            },
            {
                "name": "数据统计",
                "code": "SiteStatistics",
                "path": "/site/statistics",
                "icon": "lucide:clock",
                "component": "/site/statistics/index",
                "sort_order": 2,
                "level": 2,
                "permission_code": "site:view",
            },
            {
                "name": "刷流任务",
                "code": "BrushTask",
                "path": "/brush",
                "icon": "lucide:menu",
                "component": "/brush/index",
                "sort_order": 3,
                "level": 2,
                "permission_code": "site:manage",
            },
            {
                "name": "站点资源",
                "code": "SiteResources",
                "path": "/site/resources",
                "icon": "lucide:database",
                "component": "/site/resources/index",
                "sort_order": 4,
                "level": 2,
                "permission_code": "site:view",
            },
        ],
    },
    {
        "name": "订阅管理",
        "code": "Rss",
        "path": "",
        "icon": "lucide:rss",
        "sort_order": 5,
        "level": 1,
        "permission_code": "rss:view",
        "children": [
            {
                "name": "电影订阅",
                "code": "MovieRss",
                "path": "/rss/movie",
                "icon": "lucide:film",
                "component": "/rss/movie/index",
                "sort_order": 1,
                "level": 2,
                "permission_code": "rss:view",
            },
            {
                "name": "电视剧订阅",
                "code": "TvRss",
                "path": "/rss/tv",
                "icon": "lucide:tv",
                "component": "/rss/tv/index",
                "sort_order": 2,
                "level": 2,
                "permission_code": "rss:view",
            },
            {
                "name": "订阅历史",
                "code": "RssHistory",
                "path": "/rss/history",
                "icon": "lucide:history",
                "component": "/rss/history/index",
                "sort_order": 3,
                "level": 2,
                "permission_code": "rss:view",
            },
            {
                "name": "订阅日历",
                "code": "RssCalendar",
                "path": "/rss/calendar",
                "icon": "lucide:calendar-days",
                "component": "/rss/calendar/index",
                "sort_order": 4,
                "level": 2,
                "permission_code": "rss:view",
            },
            {
                "name": "自定义订阅",
                "code": "UserRss",
                "path": "/rss/user",
                "icon": "lucide:file-text",
                "component": "/rss/user/index",
                "sort_order": 5,
                "level": 2,
                "permission_code": "rss:manage",
            },
        ],
    },
    {
        "name": "下载管理",
        "code": "Download",
        "path": "",
        "icon": "lucide:download",
        "sort_order": 6,
        "level": 1,
        "permission_code": "download:view",
        "children": [
            {
                "name": "正在下载",
                "code": "Downloading",
                "path": "/download/downloading",
                "icon": "lucide:loader",
                "component": "/download/downloading/index",
                "sort_order": 1,
                "level": 2,
                "permission_code": "download:view",
            },
            {
                "name": "近期下载",
                "code": "DownloadHistory",
                "path": "/download/history",
                "icon": "lucide:clock",
                "component": "/download/history/index",
                "sort_order": 2,
                "level": 2,
                "permission_code": "download:view",
            },
            {
                "name": "自动删种",
                "code": "TorrentRemove",
                "path": "/download/torrent-remove",
                "icon": "lucide:trash-2",
                "component": "/download/torrent-remove/index",
                "sort_order": 3,
                "level": 2,
                "permission_code": "download:manage",
            },
            {
                "name": "下载设置",
                "code": "DownloadSettings",
                "path": "/download/settings",
                "icon": "lucide:sliders-horizontal",
                "component": "/download/settings/index",
                "sort_order": 4,
                "level": 2,
                "permission_code": "download:manage",
            },
        ],
    },
    {
        "name": "媒体整理",
        "code": "Rename",
        "icon": "lucide:file-text",
        "sort_order": 7,
        "level": 1,
        "permission_code": "library:manage",
        "children": [
            {
                "name": "识别历史",
                "code": "RenameHistory",
                "path": "/rename/history",
                "icon": "lucide:history",
                "component": "/rename/history/index",
                "sort_order": 1,
                "level": 2,
                "permission_code": "library:view",
            },
            {
                "name": "文件管理",
                "code": "RenameMediafile",
                "path": "/rename/mediafile",
                "icon": "lucide:folder-open",
                "component": "/rename/mediafile/index",
                "sort_order": 2,
                "level": 2,
                "permission_code": "library:manage",
            },
            {
                "name": "未识别列表",
                "code": "RenameUnidentification",
                "path": "/rename/unidentification",
                "icon": "lucide:help-circle",
                "component": "/rename/unidentification/index",
                "sort_order": 3,
                "level": 2,
                "permission_code": "library:manage",
            },
            {
                "name": "TMDB 黑名单",
                "code": "RenameBlacklist",
                "path": "/rename/blacklist",
                "icon": "lucide:shield-ban",
                "component": "/rename/blacklist/index",
                "sort_order": 4,
                "level": 2,
                "permission_code": "library:manage",
            },
        ],
    },
    {
        "name": "服务",
        "code": "Service",
        "icon": "lucide:layout-grid",
        "sort_order": 8,
        "level": 1,
        "permission_code": "service:view",
        "children": [
            {
                "name": "服务面板",
                "code": "ServicePanel",
                "path": "/service/panel",
                "icon": "lucide:layout-grid",
                "component": "/service/panel/index",
                "sort_order": 1,
                "level": 2,
                "permission_code": "service:view",
            },
            {
                "name": "调度任务",
                "code": "SchedulerJobs",
                "path": "/service/scheduler",
                "icon": "lucide:clock",
                "component": "/scheduler/jobs/index",
                "sort_order": 2,
                "level": 2,
                "permission_code": "service:view",
            },
        ],
    },
    {
        "name": "系统设置",
        "code": "System",
        "icon": "lucide:settings",
        "sort_order": 9,
        "level": 1,
        "permission_code": "setting:view",
        "children": [
            {
                "name": "基础设置",
                "code": "SystemBasic",
                "path": "/system/basic",
                "icon": "lucide:sliders-horizontal",
                "component": "/system/basic/index",
                "sort_order": 1,
                "level": 2,
                "permission_code": "setting:view",
            },
            {
                "name": "媒体库设置",
                "code": "SystemLibrary",
                "path": "/system/library",
                "icon": "lucide:tv",
                "component": "/system/library/index",
                "sort_order": 2,
                "level": 2,
                "permission_code": "setting:view",
            },
            {
                "name": "目录同步",
                "code": "SystemSync",
                "path": "/system/sync",
                "icon": "lucide:refresh-cw",
                "component": "/sync/index",
                "sort_order": 3,
                "level": 2,
                "permission_code": "setting:view",
            },
            {
                "name": "下载器设置",
                "code": "SystemDownloader",
                "path": "/system/downloader",
                "icon": "lucide:download",
                "component": "/download/downloader/index",
                "sort_order": 4,
                "level": 2,
                "permission_code": "setting:view",
            },
            {
                "name": "索引器设置",
                "code": "SystemIndexer",
                "path": "/system/indexer",
                "icon": "lucide:search",
                "component": "/service/indexer/index",
                "sort_order": 5,
                "level": 2,
                "permission_code": "setting:view",
            },
            {
                "name": "媒体服务器",
                "code": "SystemMediaserver",
                "path": "/system/mediaserver",
                "icon": "lucide:server",
                "component": "/service/mediaserver/index",
                "sort_order": 6,
                "level": 2,
                "permission_code": "setting:view",
            },
            {
                "name": "通知设置",
                "code": "SystemNotification",
                "path": "/system/notification",
                "icon": "lucide:bell",
                "component": "/service/notification/index",
                "sort_order": 7,
                "level": 2,
                "permission_code": "setting:view",
            },
            {
                "name": "自定义识别词",
                "code": "SystemWords",
                "path": "/system/words",
                "icon": "lucide:file-text",
                "component": "/words/index",
                "sort_order": 8,
                "level": 2,
                "permission_code": "setting:view",
            },
            {
                "name": "过滤规则",
                "code": "SystemFilter",
                "path": "/system/filter",
                "icon": "lucide:funnel",
                "component": "/filter/rule/index",
                "sort_order": 9,
                "level": 2,
                "permission_code": "setting:view",
            },
            {
                "name": "用户管理",
                "code": "SystemUsers",
                "path": "/system/users",
                "icon": "lucide:users",
                "component": "/system/users/index",
                "sort_order": 10,
                "level": 2,
                "permission_code": "user:view",
            },
            {
                "name": "角色管理",
                "code": "SystemRoles",
                "path": "/system/roles",
                "icon": "lucide:shield",
                "component": "/system/roles/index",
                "sort_order": 11,
                "level": 2,
                "permission_code": "role:view",
            },
            {
                "name": "菜单管理",
                "code": "SystemMenus",
                "path": "/system/menus",
                "icon": "lucide:menu",
                "component": "/system/menus/index",
                "sort_order": 12,
                "level": 2,
                "permission_code": "menu:view",
            },
            {
                "name": "API Key 管理",
                "code": "SystemAPIKey",
                "path": "/system/apikey",
                "icon": "lucide:key",
                "component": "/system/apikey/index",
                "sort_order": 13,
                "level": 2,
                "permission_code": "apikey:view",
            },
        ],
    },
    {
        "name": "插件中心",
        "code": "Plugin",
        "icon": "lucide:puzzle",
        "sort_order": 10,
        "level": 1,
        "permission_code": "plugin:view",
        "children": [
            {
                "name": "插件市场",
                "code": "PluginMarket",
                "path": "/plugin/market",
                "icon": "lucide:store",
                "component": "/plugin/market/index",
                "sort_order": 1,
                "level": 2,
                "permission_code": "plugin:view",
            },
            {
                "name": "已安装插件",
                "code": "PluginInstalled",
                "path": "/plugin/installed",
                "icon": "lucide:box",
                "component": "/plugin/installed/index",
                "sort_order": 2,
                "level": 2,
                "permission_code": "plugin:view",
            },
        ],
    },
    {
        "name": "日志",
        "code": "Logs",
        "path": "/logs",
        "icon": "lucide:scroll-text",
        "component": "/system/logs/index",
        "sort_order": 11,
        "level": 1,
        "permission_code": "log:view",
    },
    {
        "name": "关于",
        "code": "About",
        "path": "/about",
        "icon": "lucide:copyright",
        "component": "/_core/about/index",
        "sort_order": 9999,
        "level": 1,
        "permission_code": "",
    },
]


# 默认角色定义
DEFAULT_ROLES = [
    {
        "name": "超级管理员",
        "code": "superadmin",
        "description": "拥有系统所有权限",
        "level": 1,
        "permissions": [],
        "menus": [],
    },
    {
        "name": "管理员",
        "code": "admin",
        "description": "拥有大部分管理权限",
        "level": 10,
        "permissions": [
            "user:view",
            "user:create",
            "user:update",
            "user:delete",
            "role:view",
            "role:create",
            "role:update",
            "role:delete",
            "permission:view",
            "permission:update",
            "menu:view",
            "menu:create",
            "menu:update",
            "menu:delete",
            "setting:view",
            "setting:update",
            "library:view",
            "library:manage",
            "site:view",
            "site:manage",
            "download:view",
            "download:manage",
            "rss:view",
            "rss:manage",
            "search:view",
            "search:execute",
            "discovery:view",
            "discovery:manage",
            "service:view",
            "service:manage",
            "plugin:view",
            "plugin:manage",
            "log:view",
        ],
        "menus": [
            "Home",
            "Dashboard",
            "MediaSearch",
            "Discovery",
            "Ranking",
            "DoubanMovie",
            "DoubanTv",
            "TmdbMovie",
            "TmdbTv",
            "Bangumi",
            "DiscoveryRecommend",
            "Site",
            "SiteMaintenance",
            "SiteStatistics",
            "BrushTask",
            "SiteResources",
            "Rss",
            "MovieRss",
            "TvRss",
            "RssHistory",
            "RssCalendar",
            "UserRss",
            "Download",
            "Downloading",
            "DownloadHistory",
            "TorrentRemove",
            "DownloadSettings",
            "Rename",
            "RenameHistory",
            "RenameMediafile",
            "RenameUnidentification",
            "RenameBlacklist",
            "Service",
            "ServicePanel",
            "SchedulerJobs",
            "Logs",
            "System",
            "SystemBasic",
            "SystemLibrary",
            "SystemSync",
            "SystemDownloader",
            "SystemIndexer",
            "SystemMediaserver",
            "SystemNotification",
            "SystemWords",
            "SystemFilter",
            "SystemUsers",
            "SystemRoles",
            "SystemMenus",
            "Plugin",
            "PluginMarket",
            "PluginInstalled",
            "About",
        ],
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
            "search:view",
            "search:execute",
            "discovery:view",
            "service:view",
        ],
        "menus": [
            "Home",
            "Dashboard",
            "MediaSearch",
            "Discovery",
            "Ranking",
            "DoubanMovie",
            "DoubanTv",
            "TmdbMovie",
            "TmdbTv",
            "Bangumi",
            "DiscoveryRecommend",
            "Site",
            "SiteMaintenance",
            "SiteStatistics",
            "SiteResources",
            "Rss",
            "MovieRss",
            "TvRss",
            "RssHistory",
            "RssCalendar",
            "Download",
            "Downloading",
            "DownloadHistory",
            "Rename",
            "RenameHistory",
            "Service",
            "ServicePanel",
            "About",
        ],
    },
    {
        "name": "访客",
        "code": "guest",
        "description": "仅拥有查看权限",
        "level": 200,
        "permissions": [
            "library:view",
            "search:view",
            "discovery:view",
        ],
        "menus": [
            "Home",
            "Dashboard",
            "MediaSearch",
            "Discovery",
            "Ranking",
            "DoubanMovie",
            "DoubanTv",
            "TmdbMovie",
            "TmdbTv",
            "Bangumi",
            "DiscoveryRecommend",
        ],
    },
]


def init_rbac_permissions():
    """初始化权限数据"""
    permission_repo = RBACPermissionRepositoryAdapter()
    created_count = 0

    for perm_data in DEFAULT_PERMISSIONS:
        existing = permission_repo.get_permission_by_code(perm_data["code"])
        if not existing:
            permission_repo.create_permission(
                permission_name=perm_data["name"],
                permission_code=perm_data["code"],
                permission_type=perm_data["type"],
                module=perm_data["module"],
            )
            created_count += 1
            log.info(f"【RBAC初始化】创建权限: {perm_data['name']}")

    log.info(f"【RBAC初始化】权限初始化完成，新增 {created_count} 个权限")
    return created_count


def init_rbac_menus():
    """初始化菜单数据"""
    menu_repo = RBACMenuRepositoryAdapter()
    created_count = 0

    def create_menu_recursive(menu_data, parent_id=None):
        nonlocal created_count

        existing = menu_repo.get_menu_by_code(menu_data["code"])
        if not existing:
            result = menu_repo.create_menu(
                menu_name=menu_data["name"],
                menu_code=menu_data["code"],
                parent_id=parent_id,
                path=menu_data.get("path"),
                icon=menu_data.get("icon"),
                component=menu_data.get("component"),
                sort_order=menu_data.get("sort_order", 0),
                menu_level=menu_data.get("level", 1),
                permission_code=menu_data.get("permission_code"),
                hide_in_menu=menu_data.get("hide_in_menu", 0),
            )
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

        if "children" in menu_data:
            for child_data in menu_data["children"]:
                create_menu_recursive(child_data, menu_id)

    for menu_data in DEFAULT_MENUS:
        create_menu_recursive(menu_data)

    log.info(f"【RBAC初始化】菜单初始化完成，新增 {created_count} 个菜单")
    return created_count


def init_rbac_roles():
    """初始化角色数据"""
    role_repo = RBACRoleRepositoryAdapter()
    permission_repo = RBACPermissionRepositoryAdapter()
    menu_repo = RBACMenuRepositoryAdapter()
    created_count = 0

    for role_data in DEFAULT_ROLES:
        existing = role_repo.get_role_by_code(role_data["code"])
        if not existing:
            role = role_repo.create_role(
                role_name=role_data["name"],
                role_code=role_data["code"],
                description=role_data["description"],
                role_level=role_data["level"],
            )
            created_count += 1
            log.info(f"【RBAC初始化】创建角色: {role_data['name']}")

            if role_data["permissions"]:
                permissions = permission_repo.get_permissions_by_codes(role_data["permissions"])
                permission_ids = [p.ID for p in permissions]
                if permission_ids:
                    role_repo.assign_permissions_to_role(role.ID, permission_ids)
                    log.info(f"【RBAC初始化】为角色 {role_data['name']} 分配 {len(permission_ids)} 个权限")

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
        init_rbac_permissions()
        init_rbac_menus()
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
        user_repo = RBACUserRepositoryAdapter()
        role_repo = RBACRoleRepositoryAdapter()

        existing = user_repo.get_user_by_username(admin_username)
        if existing:
            old_hash = existing.PASSWORD_HASH or ""
            if old_hash.startswith(("pbkdf2:", "scrypt:")) or not old_hash:
                from app.utils.security import generate_password_hash

                new_hash = generate_password_hash(admin_password)
                user_repo.update_user(existing.ID, password_hash=new_hash)
                log.info(f"【RBAC初始化】管理员用户 {admin_username} 密码已从旧格式迁移到 Argon2")
            else:
                log.info(f"【RBAC初始化】管理员用户 {admin_username} 已存在")
            return True

        from app.utils.security import generate_password_hash

        password_hash = generate_password_hash(admin_password)

        user = user_repo.create_user(
            username=admin_username, password_hash=password_hash, nickname="系统管理员", is_superadmin=1
        )

        superadmin_role = role_repo.get_role_by_code("superadmin")
        if superadmin_role:
            user_repo.assign_roles_to_user(user.ID, [superadmin_role.ID])

        log.info(f"【RBAC初始化】创建管理员用户: {admin_username}")
        return True
    except Exception as e:
        log.error(f"【RBAC初始化】创建管理员用户失败: {str(e)}")
        return False

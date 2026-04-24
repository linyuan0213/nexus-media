"""
Setting Pages Router - 设置相关页面
"""
import json
from typing import Optional

from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse

from api.deps import (
    get_current_user,
    get_config_service,
    get_message_service,
    get_words_service,
    get_sync_service,
    get_downloader_service,
    get_indexer_service,
    get_plugin_service,
    get_filter_service
)
from app.conf import ModuleConf
from app.db.repositories import ConfigRepository
from app.schemas.auth import UserContext
from app.services.sync_service import SyncService
from app.services.system_service import get_rmt_modes, MessageClientService
from app.services.downloader_core import DownloaderCore
from app.services.sync_core import SyncCore
from app.services.filter_service import FilterService
from app.services.rss_service import RssTaskService
from app.services.rbac_service import rbac_service
from app.services.words_service import WordsService
from app.services.plugin_service import PluginService
from app.services.indexer_service import IndexerService
from app.services.config_service import ConfigService

from .utils import templates

router = APIRouter()

# TMDB 域名列表（兼容 Flask 路由）
TMDB_API_DOMAINS = ['api.themoviedb.org', 'api.tmdb.org']



def _get_app_config(svc: Optional[ConfigService] = None):
    """获取应用配置（兼容层）"""
    if svc is None:
        svc = get_config_service()
    return svc.get_config()


@router.get("/basic", response_class=HTMLResponse)
def basic_page(
    request: Request,
    current_user: UserContext = Depends(get_current_user),
):
    """基础设置页面"""
    cfg = _get_app_config()
    proxy = cfg.get('app', {}).get("proxies", {}).get("http")
    if proxy:
        proxy = proxy.replace("http://", "")
    rmt_mode_dict = get_rmt_modes()
    
    # 获取系统配置
    from app.conf import SystemConfig
    from app.utils.types import SystemConfigKey
    custom_script_cfg = SystemConfig().get(SystemConfigKey.CustomScript)
    scraper_conf = SystemConfig().get(SystemConfigKey.UserScraperConf) or {}

    return templates.TemplateResponse(
        request, "setting/basic.html",
        {
            "Config": cfg,
            "Proxy": proxy,
            "RmtModeDict": rmt_mode_dict,
            "CurrentUser": current_user,
            "CustomScriptCfg": custom_script_cfg,
            "ScraperNfo": scraper_conf.get("scraper_nfo") or {},
            "ScraperPic": scraper_conf.get("scraper_pic") or {},
            "TmdbDomains": TMDB_API_DOMAINS
        }
    )


@router.get("/customwords", response_class=HTMLResponse)
def customwords_page(
    request: Request,
    current_user: UserContext = Depends(get_current_user),
    words_svc = Depends(get_words_service),
):
    """自定义识别词设置页面"""
    groups = words_svc.get_all_word_groups()
    return templates.TemplateResponse(
        request, "setting/customwords.html",
        {
            "Groups": groups,
            "GroupsCount": len(groups)
        }
    )


@router.get("/directorysync", response_class=HTMLResponse)
def directorysync_page(
    request: Request,
    current_user: UserContext = Depends(get_current_user),
    sync_svc: SyncService = Depends(get_sync_service),
):
    """目录同步页面"""
    rmt_mode_dict = get_rmt_modes()
    sync_paths = sync_svc.get_sync_path_conf()
    return templates.TemplateResponse(
        request, "setting/directorysync.html",
        {
            "SyncPaths": sync_paths,
            "SyncCount": len(sync_paths),
            "RmtModeDict": rmt_mode_dict
        }
    )


@router.get("/downloader", response_class=HTMLResponse)
def downloader_page(
    request: Request,
    current_user: UserContext = Depends(get_current_user),
    dl_svc: DownloaderCore = Depends(get_downloader_service),
):
    """下载器页面"""
    default_downloader = dl_svc.default_downloader_id
    downloaders = dl_svc.get_downloader_conf()
    downloaders_count = len(downloaders)
    from app.media.category import Category
    categories = {
        "电影": list(Category().movie_categorys),
        "电视剧": list(Category().tv_categorys),
        "动漫": list(Category().anime_categorys)
    }
    rmt_mode_dict = get_rmt_modes()

    return templates.TemplateResponse(
        request, "setting/downloader.html",
        {
            "Downloaders": downloaders,
            "DefaultDownloader": default_downloader,
            "DownloadersCount": downloaders_count,
            "Categories": categories,
            "RmtModeDict": rmt_mode_dict,
            "DownloaderConf": ModuleConf.DOWNLOADER_CONF
        }
    )


@router.get("/download_setting", response_class=HTMLResponse)
def download_setting_page(
    request: Request,
    current_user: UserContext = Depends(get_current_user),
    dl_svc: DownloaderCore = Depends(get_downloader_service),
):
    """下载设置页面"""
    default_download_setting = dl_svc.default_download_setting_id
    downloaders = dl_svc.get_downloader_conf_simple()
    download_setting = dl_svc.get_download_setting()
    return templates.TemplateResponse(
        request, "setting/download_setting.html",
        {
            "DownloadSetting": download_setting,
            "DefaultDownloadSetting": default_download_setting,
            "Downloaders": downloaders,
            "Count": len(download_setting)
        }
    )


@router.get("/indexer", response_class=HTMLResponse)
def indexer_page(
    request: Request,
    current_user: UserContext = Depends(get_current_user),
    idx_svc: IndexerService = Depends(get_indexer_service),
):
    """索引器页面"""
    from app.conf import SystemConfig
    from app.utils.types import SystemConfigKey
    
    indexers = idx_svc.get_builtin_indexers(check=False)
    private_count = len([item.id for item in indexers if not item.public])
    public_count = len([item.id for item in indexers if item.public])
    
    # 获取系统配置
    indexer_sites = SystemConfig().get(SystemConfigKey.UserIndexerSites)
    search_indexer = SystemConfig().get(SystemConfigKey.SearchIndexer) or 'builtin'
    indexer_config = SystemConfig().get(SystemConfigKey.IndexerConfig) or {}

    return templates.TemplateResponse(
        request, "setting/indexer.html",
        {
            "Config": _get_app_config(),
            "PrivateCount": private_count,
            "PublicCount": public_count,
            "Indexers": indexers,
            "IndexerConf": ModuleConf.INDEXER_CONF,
            "IndexerSites": indexer_sites,
            "SearchIndexer": search_indexer,
            "IndexerConfig": indexer_config,
        }
    )


@router.get("/library", response_class=HTMLResponse)
def library_page(
    request: Request,
    current_user: UserContext = Depends(get_current_user),
):
    """媒体库页面"""
    return templates.TemplateResponse(
        request, "setting/library.html",
        {"Config": _get_app_config()}
    )


@router.get("/mediaserver", response_class=HTMLResponse)
def mediaserver_page(
    request: Request,
    current_user: UserContext = Depends(get_current_user),
):
    """媒体服务器页面"""
    repo = ConfigRepository()
    media_servers = repo.get_media_servers()
    cfg = {}
    default_server = repo.get_default_media_server()
    cfg['media'] = {
        'media_server': default_server.NAME if default_server else 'emby'
    }
    for item in media_servers:
        if item.NAME:
            cfg[item.NAME] = {}
            if item.CONFIG:
                try:
                    cfg[item.NAME] = json.loads(item.CONFIG)
                except Exception:
                    pass
    return templates.TemplateResponse(
        request, "setting/mediaserver.html",
        {
            "Config": cfg,
            "MediaServerConf": ModuleConf.MEDIASERVER_CONF
        }
    )


@router.get("/notification", response_class=HTMLResponse)
def notification_page(
    request: Request,
    current_user: UserContext = Depends(get_current_user),
    msg_svc: MessageClientService = Depends(get_message_service),
):
    """通知消息页面"""
    message_clients = msg_svc.get_client()
    channels = ModuleConf.MESSAGE_CONF.get("client")
    switchs = ModuleConf.MESSAGE_CONF.get("switch")
    return templates.TemplateResponse(
        request, "setting/notification.html",
        {
            "Channels": channels,
            "Switchs": switchs,
            "ClientCount": len(message_clients),
            "MessageClients": message_clients
        }
    )


@router.get("/users", response_class=HTMLResponse)
def users_page(
    request: Request,
    current_user: UserContext = Depends(get_current_user),
):
    """用户管理页面"""
    # 直接使用 rbac_service 获取用户列表（避免跨层依赖 web.backend.user）
    users_raw, _ = rbac_service.get_users(page=1, page_size=1000)
    Users = []
    for user in users_raw:
        roles = []
        try:
            roles = [role.to_dict() for role in user.roles]
        except Exception:
            pass
        last_login = None
        if hasattr(user, 'LAST_LOGIN_AT') and user.LAST_LOGIN_AT:
            last_login = user.LAST_LOGIN_AT.strftime('%Y-%m-%d %H:%M')
        Users.append({
            "id": user.ID,
            "name": user.USERNAME,
            "username": user.USERNAME,
            "nickname": user.NICKNAME or user.USERNAME,
            "email": user.EMAIL,
            "status": user.STATUS,
            "roles": roles,
            "last_login_at": last_login,
            "pris": [role.get('role_name') for role in roles] if roles else ["普通用户"]
        })
    # 顶级菜单通过 rbac_service 获取
    top_menus_raw = rbac_service.menu_repo.get_top_menus(include_hidden=True)
    top_menus = []
    for menu in top_menus_raw:
        try:
            top_menus.append(menu.to_dict())
        except Exception:
            pass
    roles = rbac_service.get_all_roles()
    return templates.TemplateResponse(
        request, "setting/users.html",
        {
            "Users": Users,
            "UserCount": len(Users),
            "TopMenus": top_menus,
            "Roles": roles,
            "current_user": current_user
        }
    )


@router.get("/roles", response_class=HTMLResponse)
def roles_page(
    request: Request,
    current_user: UserContext = Depends(get_current_user),
):
    """角色管理页面"""
    roles = rbac_service.get_all_roles()
    permissions = rbac_service.get_all_permissions()
    menus = rbac_service.menu_repo.get_all_menus(status=1)
    return templates.TemplateResponse(
        request, "setting/roles.html",
        {
            "Roles": roles,
            "Permissions": permissions,
            "Menus": menus,
            "current_user": current_user
        }
    )


@router.get("/menus", response_class=HTMLResponse)
def menus_page(
    request: Request,
    current_user: UserContext = Depends(get_current_user),
):
    """菜单管理页面"""
    menus = rbac_service.menu_repo.get_all_menus()
    menu_tree = rbac_service.get_menu_tree(include_hidden=True)
    top_menus = rbac_service.menu_repo.get_top_menus(include_hidden=True)
    permissions = rbac_service.get_all_permissions()
    return templates.TemplateResponse(
        request, "setting/menus.html",
        {
            "Menus": menus,
            "MenuTree": menu_tree,
            "TopMenus": top_menus,
            "Permissions": permissions,
            "current_user": current_user
        }
    )


def _get_script_path():
    """获取脚本路径（兼容层）"""
    return get_config_service().get_script_path()


@router.get("/filterrule", response_class=HTMLResponse)
def filterrule_page(
    request: Request,
    current_user: UserContext = Depends(get_current_user),
    svc: FilterService = Depends(get_filter_service),
):
    """过滤规则设置页面"""
    RuleGroups, Init_RuleGroups = svc.get_filterrules(_get_script_path())
    return templates.TemplateResponse(
        request, "setting/filterrule.html",
        {
            "Count": len(RuleGroups),
            "RuleGroups": RuleGroups,
            "Init_RuleGroups": Init_RuleGroups
        }
    )


@router.get("/plugin", response_class=HTMLResponse)
def plugin_page(
    request: Request,
    current_user: UserContext = Depends(get_current_user),
):
    """插件页面"""
    plugins = get_plugin_service().get_plugins_conf(user_level=2)
    return templates.TemplateResponse(
        request, "setting/plugin.html",
        {
            "Plugins": plugins,
            "Count": len(plugins)
        }
    )


@router.get("/open", response_class=HTMLResponse)
def open_app_page(request: Request):
    """唤起App中转页面"""
    return templates.TemplateResponse(request, "openapp.html", {})

"""
Base Pages Router - 登录、主页、导航等核心页面
"""
from typing import Optional

from fastapi import APIRouter, Request, Depends, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.status import HTTP_302_FOUND

from api.deps import (
    get_current_user,
    get_current_user_optional,
    get_config_service,
    get_media_library_service,
    get_site_service,
    get_indexer_service,
)
from app.conf import ModuleConf
from app.db.repositories import ConfigRepository
from app.schemas.auth import UserContext
from app.services.system_service import get_rmt_modes, get_commands
from app.services.media_service import MediaLibraryService
from app.services.rbac_service import rbac_service
from app.utils import SystemUtils
from version import APP_VERSION
import log

from .utils import templates

router = APIRouter()


def _get_login_wallpaper():
    """获取登录壁纸（兼容层）"""
    from app.utils.wallpaper import get_login_wallpaper
    return get_login_wallpaper()


def _get_app_config():
    """获取应用配置（兼容层）"""
    return get_config_service().get_config()


def _get_version():
    """获取当前版本号"""
    return APP_VERSION


# ---------------------------------------------------------------------------
# 登录页面
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
def login_page(
    request: Request,
    next: Optional[str] = Query(None, alias="next"),
    current_user: Optional[UserContext] = Depends(get_current_user_optional),
):
    go_page = next or ""
    if go_page.startswith('/'):
        go_page = go_page[1:]

    if current_user:
        redirect_url = f"/web#{go_page}" if go_page else "/web"
        return RedirectResponse(url=redirect_url, status_code=HTTP_302_FOUND)

    image_code, img_title, img_link = _get_login_wallpaper()
    return templates.TemplateResponse(
        request, "login.html",
        {
            "GoPage": go_page,
            "image_code": image_code,
            "img_title": img_title,
            "img_link": img_link,
            "err_msg": ""
        }
    )


@router.post("/", response_class=HTMLResponse)
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form(""),
    remember: Optional[str] = Form(None),
    media_library_svc = Depends(get_media_library_service),
):
    go_page = next
    if go_page.startswith('/'):
        go_page = go_page[1:]

    if not username:
        image_code, img_title, img_link = _get_login_wallpaper()
        return templates.TemplateResponse(
            request, "login.html",
            {
                "GoPage": go_page,
                "image_code": image_code,
                "img_title": img_title,
                "img_link": img_link,
                "err_msg": "请输入用户名"
            }
        )

    # 使用 RBAC 服务进行认证（完全避免 web.backend.user）
    ok, result = rbac_service.authenticate_user(username, password)
    if not ok:
        image_code, img_title, img_link = _get_login_wallpaper()
        return templates.TemplateResponse(
            request, "login.html",
            {
                "GoPage": go_page,
                "image_code": image_code,
                "img_title": img_title,
                "img_link": img_link,
                "err_msg": "用户名或密码错误"
            }
        )

    user = result
    request.session["user_id"] = user.ID
    request.session["username"] = user.USERNAME

    try:
        from datetime import datetime
        rbac_service.user_repo.update_user(
            user.ID,
            LAST_LOGIN_AT=datetime.now(),
            LAST_LOGIN_IP=request.client.host if request.client else ""
        )
    except Exception as e:
        log.warn(f"更新最后登录时间失败: {e}")

    if remember:
        request.session.permanent = True

    cfg_svc = get_config_service()
    cfg_svc.current_user = user.USERNAME

    try:
        media_library_svc.init_config()
    except Exception as e:
        log.warn(f"初始化媒体服务器配置失败: {e}")

    redirect_url = f"/web#{go_page}" if go_page else "/web"
    return RedirectResponse(url=redirect_url, status_code=HTTP_302_FOUND)


# ---------------------------------------------------------------------------
# 导航页面
# ---------------------------------------------------------------------------

@router.get("/web", response_class=HTMLResponse)
def web_page(
    request: Request,
    next: Optional[str] = Query(None, alias="next"),
    current_user: UserContext = Depends(get_current_user),
    site_svc = Depends(get_site_service),
    indexer_svc = Depends(get_indexer_service),
):
    go_page = next or ""
    cfg = _get_app_config()
    system_flag = SystemUtils.get_system()
    sync_mod = cfg.get('media', {}).get('default_rmt_mode') or "link"
    tmdb_flag = 1 if cfg.get('app', {}).get('rmt_tmdbkey') else 0
    default_path = cfg.get('media', {}).get('media_default_path')

    rmt_mode_dict = get_rmt_modes()
    restype_dict = ModuleConf.TORRENT_SEARCH_PARAMS.get("restype")
    pix_dict = ModuleConf.TORRENT_SEARCH_PARAMS.get("pix")

    try:
        site_favicons = site_svc.get_site_favicon()
    except Exception:
        site_favicons = {}

    try:
        indexers = indexer_svc.get_indexers()
    except Exception:
        indexers = []

    search_source = "douban" if cfg.get("laboratory", {}).get("use_douban_titles") else "tmdb"

    try:
        user_id = current_user.user_id if current_user else None
        menus = rbac_service.get_user_menus(user_id) if user_id else []
        menus = [{
            "name": m.name,
            "code": m.code,
            "path": m.path,
            "icon": m.icon,
            "component": m.component,
            "sort_order": m.sort_order
        } for m in menus]
    except Exception:
        menus = []

    commands = get_commands()

    try:
        from app.conf.systemconfig import SystemConfig
        from app.utils.types import SystemConfigKey
        custom_script_cfg = SystemConfig().get(SystemConfigKey.CustomScript)
    except Exception:
        custom_script_cfg = None

    return templates.TemplateResponse(
        request, "navigation.html",
        {
            "GoPage": go_page,
            "CurrentUser": current_user,
            "SystemFlag": system_flag.value,
            "TMDBFlag": tmdb_flag,
            "AppVersion": _get_version(),
            "RestypeDict": restype_dict,
            "PixDict": pix_dict,
            "SyncMod": sync_mod,
            "SiteFavicons": site_favicons,
            "RmtModeDict": rmt_mode_dict,
            "Indexers": indexers,
            "SearchSource": search_source,
            "DefaultPath": default_path,
            "Menus": menus,
            "Commands": commands,
            "CustomScriptCfg": custom_script_cfg,
        }
    )


# ---------------------------------------------------------------------------
# 首页
# ---------------------------------------------------------------------------

@router.get("/index", response_class=HTMLResponse)
def index_page(
    request: Request,
    current_user: UserContext = Depends(get_current_user),
    media_library_svc: MediaLibraryService = Depends(get_media_library_service),
):
    default_server = ConfigRepository().get_default_media_server()
    cfg = _get_app_config()
    ms_type = default_server.NAME if default_server else cfg.get('media', {}).get('media_server') or 'emby'

    server_success = False
    media_counts = {}
    try:
        result = media_library_svc.get_media_count()
        if result:
            media_counts = result
            server_success = True
    except Exception as e:
        log.warn(f"获取媒体库统计失败: {e}")

    activity = []
    try:
        activity = media_library_svc.get_play_history() or []
    except Exception as e:
        log.warn(f"获取播放历史失败: {e}")

    library_spaces = {}
    try:
        space_info = media_library_svc.get_space_info()
        library_spaces = {
            "UsedPercent": space_info.used_percent,
            "FreeSpace": space_info.free_space,
            "UsedSpace": space_info.used_space,
            "TotalSpace": space_info.total_space,
        }
    except Exception as e:
        log.warn(f"获取存储空间失败: {e}")

    libraries = []
    library_sync_conf = []
    try:
        libraries = media_library_svc.get_libraries() or []
    except Exception as e:
        log.warn(f"获取媒体库列表失败: {e}")

    resumes = []
    try:
        resumes = media_library_svc.get_resume() or []
    except Exception as e:
        log.warn(f"获取继续观看失败: {e}")

    latests = []
    try:
        latests = media_library_svc.get_latest() or []
    except Exception as e:
        log.warn(f"获取最近添加失败: {e}")

    request_host = request.url.hostname or request.headers.get('host', '').split(':')[0]

    return templates.TemplateResponse(
        request, "index.html",
        {
            "ServerSucess": server_success,
            "MSType": ms_type,
            "MediaCount": {
                'MovieCount': media_counts.get("Movie", 0),
                'SeriesCount': media_counts.get("Series", 0),
                'SongCount': media_counts.get("Music", 0),
                "EpisodeCount": media_counts.get("Episodes", 0)
            },
            "UserCount": media_counts.get("User", 0),
            "Activitys": activity,
            "LibrarySpaces": library_spaces,
            "Librarys": libraries,
            "LibrarySyncConf": library_sync_conf,
            "Resumes": resumes,
            "Latests": latests,
            "request_host": request_host,
        }
    )

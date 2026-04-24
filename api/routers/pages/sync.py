"""
Sync Pages Router - 同步、历史、日志、服务、调度等页面
"""
import os
from math import floor
from typing import Optional

from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse

from api.deps import (
    get_current_user,
    get_config_service,
    get_filter_service,
    get_sync_service,
    get_transfer_history_service,
    get_downloader_service,
    get_tmdb_blacklist_helper,
)
from app.conf import ModuleConf
from app.schemas.auth import UserContext
from app.services.system_service import get_rmt_modes
from app.services.config_service import ConfigService
from app.utils.pagination import get_page_range
import log

from .utils import templates

router = APIRouter()


# 服务配置常量（兼容旧接口，从 web.backend.user 迁移）
_SERVICE_CONF = {
    'rssdownload': {'name': '电影/电视剧订阅', 'icon': 'cloud-download', 'color': 'blue', 'level': 2},
    'subscribe_search_all': {'name': '订阅搜索', 'icon': 'search', 'color': 'blue', 'level': 2},
    'pttransfer': {'name': '下载文件转移', 'icon': 'replace', 'color': 'green', 'level': 2},
    'sync': {'name': '目录同步', 'time': '实时监控', 'icon': 'refresh-cw', 'color': 'orange', 'level': 1},
    'blacklist': {'name': '清理转移缓存', 'time': '手动', 'state': 'OFF', 'icon': 'eraser', 'color': 'red', 'level': 1},
    'rsshistory': {'name': '清理RSS缓存', 'time': '手动', 'state': 'OFF', 'icon': 'eraser', 'color': 'purple', 'level': 2},
    'nametest': {'name': '名称识别测试', 'time': '', 'state': 'OFF', 'icon': 'type', 'color': 'lime', 'level': 1},
    'ruletest': {'name': '过滤规则测试', 'time': '', 'state': 'OFF', 'icon': 'sliders-horizontal', 'color': 'yellow', 'level': 2},
    'nettest': {'name': '网络连通性测试', 'time': '', 'state': 'OFF', 'icon': 'network', 'color': 'cyan', 'targets': ModuleConf.NETTEST_TARGETS if hasattr(ModuleConf, 'NETTEST_TARGETS') else [], 'level': 1},
}


def _get_pt_config(svc: Optional[ConfigService] = None):
    """获取 PT 配置（兼容层）"""
    if svc is None:
        svc = get_config_service()
    return svc.get_pt_config()


def _get_media_config(svc: Optional[ConfigService] = None):
    """获取媒体配置（兼容层）"""
    if svc is None:
        svc = get_config_service()
    return svc.get_media_config()


@router.get("/service", response_class=HTMLResponse)
def service_page(
    request: Request,
    current_user: UserContext = Depends(get_current_user),
    filter_svc = Depends(get_filter_service),
    sync_svc = Depends(get_sync_service),
):
    """服务页面"""
    rule_groups = filter_svc.get_rule_groups()
    sync_paths = sync_svc.get_sync_path_conf()

    services = {k: dict(v) for k, v in _SERVICE_CONF.items()}
    pt = _get_pt_config()
    if "rssdownload" in services:
        pt_check_interval = pt.get('pt_check_interval')
        if str(pt_check_interval).isdigit():
            tim_rssdownload = str(round(int(pt_check_interval) / 60)) + " 分钟"
            rss_state = 'ON'
        else:
            tim_rssdownload = ""
            rss_state = 'OFF'
        services['rssdownload'].update({
            'time': tim_rssdownload,
            'state': rss_state,
        })

    if "subscribe_search_all" in services:
        search_rss_interval = pt.get('search_rss_interval')
        if str(search_rss_interval).isdigit():
            if int(search_rss_interval) < 2:
                search_rss_interval = 2
            tim_rsssearch = str(int(search_rss_interval)) + " 小时"
            rss_search_state = 'ON'
        else:
            tim_rsssearch = ""
            rss_search_state = 'OFF'
        services['subscribe_search_all'].update({
            'time': tim_rsssearch,
            'state': rss_search_state,
        })

    return templates.TemplateResponse(
        request, "service.html",
        {
            "Count": len(services),
            "RuleGroups": rule_groups,
            "SyncPaths": sync_paths,
            "SchedulerTasks": services
        }
    )


@router.get("/scheduler", response_class=HTMLResponse)
def scheduler_page(
    request: Request,
    current_user: UserContext = Depends(get_current_user),
):
    """调度任务页面"""
    return templates.TemplateResponse(request, "scheduler.html", {})


@router.get("/logging", response_class=HTMLResponse)
def logging_page(
    request: Request,
    current_user: UserContext = Depends(get_current_user),
):
    """日志页面"""
    return templates.TemplateResponse(request, "logging.html", {})


@router.get("/history", response_class=HTMLResponse)
def history_page(
    request: Request,
    pagenum: Optional[str] = Query(None),
    s: Optional[str] = Query(""),
    page: Optional[str] = Query(None),
    current_user: UserContext = Depends(get_current_user),
    history_svc = Depends(get_transfer_history_service),
):
    """历史记录页面"""
    result = history_svc.get_transfer_history_page(
        search_str=s, page=page, page_num=pagenum
    )
    page_range = get_page_range(
        current_page=result.current_page,
        total_page=result.total_page)

    return templates.TemplateResponse(
        request, "rename/history.html",
        {
            "TotalCount": result.total,
            "Count": len(result.result or []),
            "Historys": result.result,
            "Search": s,
            "CurrentPage": result.current_page,
            "TotalPage": result.total_page,
            "PageRange": page_range,
            "PageNum": result.current_page
        }
    )


@router.get("/tmdbblacklist", response_class=HTMLResponse)
def tmdbblacklist_page(
    request: Request,
    pagenum: Optional[str] = Query("30"),
    s: Optional[str] = Query(""),
    page: Optional[str] = Query("1"),
    current_user: UserContext = Depends(get_current_user),
    tmdb_blacklist_helper = Depends(get_tmdb_blacklist_helper),
):
    """TMDB缓存页面"""
    page_num = int(pagenum) if pagenum else 30
    search_str = s if s else ""
    current_page = int(page) if page else 1

    tmdb_blacklist, total_count = tmdb_blacklist_helper.get_blacklist(
        search_str, current_page, page_num)
    total_page = floor(total_count / page_num) + 1
    page_range = get_page_range(
        current_page=current_page,
        total_page=total_page)

    return templates.TemplateResponse(
        request, "rename/tmdbblacklist.html",
        {
            "TotalCount": total_count,
            "Count": len(tmdb_blacklist),
            "TmdbBlacklist": tmdb_blacklist,
            "Search": search_str,
            "CurrentPage": current_page,
            "TotalPage": total_page,
            "PageRange": page_range,
            "PageNum": page_num
        }
    )


@router.get("/unidentification", response_class=HTMLResponse)
def unidentification_page(
    request: Request,
    pagenum: Optional[str] = Query(None),
    s: Optional[str] = Query(""),
    page: Optional[str] = Query(None),
    current_user: UserContext = Depends(get_current_user),
    transfer_history_svc = Depends(get_transfer_history_service),
):
    """手工识别页面"""
    result = transfer_history_svc.get_unknown_list_by_page(
        search_str=s, page=page, page_num=pagenum
    )
    page_range = get_page_range(
        current_page=result.current_page,
        total_page=result.total_page)

    return templates.TemplateResponse(
        request, "rename/unidentification.html",
        {
            "TotalCount": result.total,
            "Count": len(result.items or []),
            "Items": result.items,
            "Search": s,
            "CurrentPage": result.current_page,
            "TotalPage": result.total_page,
            "PageRange": page_range,
            "PageNum": result.current_page
        }
    )


@router.get("/mediafile", response_class=HTMLResponse)
def mediafile_page(
    request: Request,
    dir: Optional[str] = Query(None),
    current_user: UserContext = Depends(get_current_user),
    downloader_svc = Depends(get_downloader_service),
):
    """文件管理页面"""
    media_default_path = _get_media_config().get('media_default_path')
    if media_default_path:
        dir_d = media_default_path
    else:
        download_dirs = downloader_svc.get_download_visit_dirs()
        if download_dirs:
            try:
                dir_d = os.path.commonpath(download_dirs).replace("\\", "/")
            except Exception as err:
                print(str(err))
                dir_d = "/"
        else:
            dir_d = "/"

    dir_r = dir
    return templates.TemplateResponse(
        request, "rename/mediafile.html",
        {"Dir": dir_r or dir_d}
    )


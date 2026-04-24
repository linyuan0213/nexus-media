"""
RSS Pages Router - 订阅相关页面
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse

from api.deps import (
    get_current_user,
    get_filter_service,
    get_downloader_service,
    get_rss_subscription_service,
    get_rss_task_service,
)
from app.conf import ModuleConf

from .utils import templates

router = APIRouter()


@router.get("/movie_rss", response_class=HTMLResponse)
def movie_rss_page(
    request: Request,
    current_user: str = Depends(get_current_user),
    rss_svc = Depends(get_rss_subscription_service),
    filter_svc = Depends(get_filter_service),
    dl_svc = Depends(get_downloader_service),
):
    """电影订阅页面"""
    rss_items = rss_svc.get_movie_rss_list()
    rule_groups = {str(group["id"]): group["name"]
                   for group in filter_svc.get_rule_groups()}
    download_settings = dl_svc.get_download_setting()
    
    return templates.TemplateResponse(
        request, "rss/movie_rss.html",
        {
            "Count": len(rss_items) if rss_items else 0,
            "RuleGroups": rule_groups,
            "DownloadSettings": download_settings,
            "Items": rss_items or []
        }
    )


@router.get("/tv_rss", response_class=HTMLResponse)
def tv_rss_page(
    request: Request,
    current_user: str = Depends(get_current_user),
    rss_svc = Depends(get_rss_subscription_service),
    filter_svc = Depends(get_filter_service),
    dl_svc = Depends(get_downloader_service),
):
    """电视剧订阅页面"""
    rss_items = rss_svc.get_tv_rss_list()
    rule_groups = {str(group["id"]): group["name"]
                   for group in filter_svc.get_rule_groups()}
    download_settings = dl_svc.get_download_setting()
    
    return templates.TemplateResponse(
        request, "rss/tv_rss.html",
        {
            "Count": len(rss_items) if rss_items else 0,
            "RuleGroups": rule_groups,
            "DownloadSettings": download_settings,
            "Items": rss_items or []
        }
    )


@router.get("/rss_history", response_class=HTMLResponse)
def rss_history_page(
    request: Request,
    t: Optional[str] = Query(None),
    current_user: str = Depends(get_current_user),
    rss_svc = Depends(get_rss_subscription_service),
):
    """订阅历史页面"""
    rss_history = rss_svc.get_rss_history(mtype=t)
    return templates.TemplateResponse(
        request, "rss/rss_history.html",
        {
            "Count": len(rss_history) if rss_history else 0,
            "Items": rss_history or [],
            "Type": t
        }
    )


@router.get("/rss_calendar", response_class=HTMLResponse)
def rss_calendar_page(
    request: Request,
    current_user: str = Depends(get_current_user),
    rss_svc = Depends(get_rss_subscription_service),
):
    """订阅日历页面"""
    today = datetime.strftime(datetime.now(), '%Y-%m-%d')
    rss_movie_items = rss_svc.get_movie_rss_items()
    rss_tv_items = rss_svc.get_tv_rss_items()
    
    return templates.TemplateResponse(
        request, "rss/rss_calendar.html",
        {
            "Today": today,
            "RssMovieItems": rss_movie_items,
            "RssTvItems": rss_tv_items
        }
    )


@router.get("/user_rss", response_class=HTMLResponse)
def user_rss_page(
    request: Request,
    current_user: str = Depends(get_current_user),
    rss_task_svc = Depends(get_rss_task_service),
    filter_svc = Depends(get_filter_service),
    dl_svc = Depends(get_downloader_service),
):
    """自定义订阅页面"""
    tasks = rss_task_svc.get_rsstask_info()
    rss_parsers = rss_task_svc.get_userrss_parser()
    rule_groups = {str(group["id"]): group["name"]
                   for group in filter_svc.get_rule_groups()}
    download_settings = {did: attr["name"] for did, attr
                        in dl_svc.get_download_setting().items()}
    restype_dict = ModuleConf.TORRENT_SEARCH_PARAMS.get("restype")
    pix_dict = ModuleConf.TORRENT_SEARCH_PARAMS.get("pix")
    return templates.TemplateResponse(
        request, "rss/user_rss.html",
        {
            "Tasks": tasks,
            "Count": len(tasks),
            "RssParsers": rss_parsers,
            "RuleGroups": rule_groups,
            "RestypeDict": restype_dict,
            "PixDict": pix_dict,
            "DownloadSettings": download_settings
        }
    )


@router.get("/rss_parser", response_class=HTMLResponse)
def rss_parser_page(
    request: Request,
    current_user: str = Depends(get_current_user),
    rss_task_svc = Depends(get_rss_task_service),
):
    """RSS解析器页面"""
    rss_parsers = rss_task_svc.get_userrss_parser()
    return templates.TemplateResponse(
        request, "rss/rss_parser.html",
        {
            "RssParsers": rss_parsers,
            "Count": len(rss_parsers)
        }
    )

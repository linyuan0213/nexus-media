"""
Site Pages Router - 站点相关页面
"""
from math import floor
from typing import Optional

from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse

from api.deps import (
    get_current_user,
    get_site_service,
    get_indexer_service,
    get_filter_service,
    get_downloader_service,
    get_drissionpage_helper,
    get_brush_task_service,
)
from app.conf import ModuleConf
from app.services.filter_service import FilterService
from app.services.downloader_core import DownloaderCore
from app.services.brush_core import BrushTaskService
from app.services.site_service import SiteService
from app.services.indexer_service import IndexerService

from .utils import templates

router = APIRouter()




@router.get("/site", response_class=HTMLResponse)
def site_page(
    request: Request,
    current_user: str = Depends(get_current_user),
    site_svc = Depends(get_site_service),
    filter_svc = Depends(get_filter_service),
    dl_svc = Depends(get_downloader_service),
    drission_helper = Depends(get_drissionpage_helper),
):
    """站点维护页面"""
    cfg_sites = site_svc.get_sites()
    rule_groups = {str(group["id"]): group["name"]
                   for group in filter_svc.get_rule_groups()}
    download_settings = {did: attr["name"] for did, attr
                        in dl_svc.get_download_setting().items()}
    try:
        chrome_ok = drission_helper.get_status()
    except Exception:
        chrome_ok = False
    cookiecloud_cfg = {}  # TODO: 从 SystemConfig 获取
    cookieuserinfo_cfg = {}  # TODO: 从 SystemConfig 获取
    
    return templates.TemplateResponse(
        request, "site/site.html",
        {
            "Sites": cfg_sites,
            "RuleGroups": rule_groups,
            "DownloadSettings": download_settings,
            "ChromeOk": chrome_ok,
            "CookieCloudCfg": cookiecloud_cfg,
            "CookieUserInfoCfg": cookieuserinfo_cfg
        }
    )


@router.get("/sitelist", response_class=HTMLResponse)
def sitelist_page(
    request: Request,
    current_user: str = Depends(get_current_user),
    idx_svc = Depends(get_indexer_service),
):
    """站点列表页面"""
    indexer_sites = idx_svc.get_builtin_indexers(check=False)
    return templates.TemplateResponse(
        request, "site/sitelist.html",
        {
            "Sites": indexer_sites,
            "Count": len(indexer_sites)
        }
    )


@router.get("/resources", response_class=HTMLResponse)
def resources_page(
    request: Request,
    site: Optional[str] = Query(None),
    title: Optional[str] = Query(None),
    page: Optional[str] = Query("0"),
    keyword: Optional[str] = Query(None),
    current_user: str = Depends(get_current_user),
    site_svc = Depends(get_site_service),
):
    """站点资源页面"""
    result_dto = site_svc.list_site_resources(
        index_id=site,
        page=page,
        keyword=keyword
    )
    results = result_dto.data if result_dto.success else []
    
    return templates.TemplateResponse(
        request, "site/resources.html",
        {
            "Results": results,
            "SiteId": site,
            "Title": title,
            "KeyWord": keyword,
            "TotalCount": len(results),
            "PageRange": range(0, 10),
            "CurrentPage": int(page),
            "TotalPage": 10
        }
    )


@router.get("/statistics", response_class=HTMLResponse)
def statistics_page(
    request: Request,
    refresh_site: list = Query(default=[]),
    refresh_force: bool = Query(False),
    current_user: str = Depends(get_current_user),
    site_svc = Depends(get_site_service),
):
    """数据统计页面"""
    total_upload = 0
    total_download = 0
    total_seeding_size = 0
    total_seeding = 0
    
    site_names = []
    site_uploads = []
    site_downloads = []
    site_ratios = []
    site_errs = {}
    
    site_data = site_svc._site_user_info.get_site_data(
        specify_sites=refresh_site, force=refresh_force)
    
    if isinstance(site_data, dict):
        for name, data in site_data.items():
            if not data:
                continue
            up = data.get("upload", 0)
            dl = data.get("download", 0)
            ratio = data.get("ratio", 0)
            seeding = data.get("seeding", 0)
            seeding_size = data.get("seeding_size", 0)
            err_msg = data.get("err_msg", "")
            
            site_errs.update({name: err_msg})
            
            if not up and not dl and not ratio:
                continue
            if not str(up).isdigit() or not str(dl).isdigit():
                continue
            if name not in site_names:
                site_names.append(name)
                total_upload += int(up)
                total_download += int(dl)
                total_seeding += int(seeding)
                total_seeding_size += int(seeding_size)
                site_uploads.append(int(up))
                site_downloads.append(int(dl))
                site_ratios.append(round(float(ratio), 1))
    
    site_user_statistics = site_svc.get_site_user_statistics(
        sites="", encoding="DICT", sort_by="", sort_on="", site_hash=""
    )
    
    return templates.TemplateResponse(
        request, "site/statistics.html",
        {
            "TotalDownload": total_download,
            "TotalUpload": total_upload,
            "TotalSeedingSize": total_seeding_size,
            "TotalSeeding": total_seeding,
            "SiteDownloads": site_downloads,
            "SiteUploads": site_uploads,
            "SiteRatios": site_ratios,
            "SiteNames": site_names,
            "SiteErr": site_errs,
            "SiteUserStatistics": site_user_statistics
        }
    )


@router.get("/brushtask", response_class=HTMLResponse)
def brushtask_page(
    request: Request,
    current_user: str = Depends(get_current_user),
    site_svc = Depends(get_site_service),
    dl_svc = Depends(get_downloader_service),
    brush_svc: BrushTaskService = Depends(get_brush_task_service),
):
    """刷流任务页面"""
    cfg_sites = site_svc.get_sites(brush=True)
    downloaders = dl_svc.get_downloader_conf_simple()
    tasks = brush_svc.get_brushtask_info()
    
    return templates.TemplateResponse(
        request, "site/brushtask.html",
        {
            "Count": len(tasks),
            "Sites": cfg_sites,
            "Tasks": tasks,
            "Downloaders": downloaders
        }
    )

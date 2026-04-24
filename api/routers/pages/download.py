"""
Download Pages Router - 下载相关页面
"""
from typing import Optional

from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse

from api.deps import get_current_user, get_download_service, get_downloader_service, get_torrent_remover_service
from app.conf import ModuleConf
from app.services.downloader_core import DownloaderCore
from app.services.torrentremover_core import TorrentRemoverService
from app.services.download_service import DownloadService

from .utils import templates

router = APIRouter()




@router.get("/downloading", response_class=HTMLResponse)
def downloading_page(
    request: Request,
    current_user: str = Depends(get_current_user),
    dl_svc: DownloadService = Depends(get_download_service),
):
    """正在下载页面"""
    disp_torrents = dl_svc.get_downloading_with_media_info()
    return templates.TemplateResponse(
        request, "download/downloading.html",
        {
            "DownloadCount": len(disp_torrents),
            "Torrents": disp_torrents
        }
    )


@router.get("/torrent_remove", response_class=HTMLResponse)
def torrent_remove_page(
    request: Request,
    current_user: str = Depends(get_current_user),
    downloader: DownloaderCore = Depends(get_downloader_service),
    torrent_remover: TorrentRemoverService = Depends(get_torrent_remover_service),
):
    """自动删种任务页面"""
    downloaders = downloader.get_downloader_conf_simple()
    torrent_remove_tasks = torrent_remover.get_torrent_remove_tasks()
    
    return templates.TemplateResponse(
        request, "download/torrent_remove.html",
        {
            "Downloaders": downloaders,
            "DownloaderConfig": ModuleConf.TORRENTREMOVER_DICT,
            "Count": len(torrent_remove_tasks),
            "TorrentRemoveTasks": torrent_remove_tasks
        }
    )

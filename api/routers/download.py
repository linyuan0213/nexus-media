"""
Download Router — FastAPI 迁移
对应原 web/controllers/download.py，复用 app/services/download_service.py
"""

import json
import os

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import (
    get_download_service,
    get_downloader_service,
    get_filetransfer_service,
    get_indexer_service,
    get_site_service,
    require_any_permission,
    require_permission,
)
from app.core.module_config import ModuleConf
from app.helper.thread_helper import ThreadHelper
from app.schemas.auth import UserContext
from app.services.download_service import DownloadService
from app.services.downloader_core import DownloaderCore as Downloader
from app.services.filetransfer_service import FileTransferService as FileTransfer
from app.services.indexer_service import IndexerService
from app.services.site_service import SiteService
from app.utils import ExceptionUtils, SystemUtils
from app.utils.response import fail, success

router = APIRouter()


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------


class EmptyRequest(BaseModel):
    data: dict | None = None


class AutoRemoveTorrentsRequest(BaseModel):
    tid: str | None = None


class CheckDownloaderRequest(BaseModel):
    did: str | None = None
    checked: bool | None = None
    flag: str | None = None


class DelDownloaderRequest(BaseModel):
    did: str | None = None


class DeleteDownloadSettingRequest(BaseModel):
    sid: str | None = None


class DeleteTorrentRemoveTaskRequest(BaseModel):
    tid: str | None = None


class DownloadRequest(BaseModel):
    id: int | None = None
    dir: str | None = None
    setting: str | None = None


class DownloadLinkRequest(BaseModel):
    site: str | None = None
    enclosure: str | None = None
    title: str | None = None
    description: str | None = None
    page_url: str | None = None
    size: str | None = None
    seeders: str | None = None
    uploadvolumefactor: str | None = None
    downloadvolumefactor: str | None = None
    dl_dir: str | None = None
    dl_setting: str | None = None


class DownloadTorrentRequest(BaseModel):
    files: list | None = None
    urls: list | None = None
    dl_dir: str | None = None
    dl_setting: str | None = None
    page_url: str | None = None
    upload_volume_factor: float | None = None
    download_volume_factor: float | None = None
    title: str | None = None
    description: str | None = None
    site: str | None = None
    size: int | None = None


class FindHardlinksRequest(BaseModel):
    files: list | None = None
    dir: str | None = None


class ResolveDownloadUrlRequest(BaseModel):
    page_url: str | None = None
    enclosure: str | None = None


class GetDownloadDirsRequest(BaseModel):
    sid: str | None = None
    site: str | None = None


class GetDownloadSettingRequest(BaseModel):
    sid: str | None = None


class GetDownloadersRequest(BaseModel):
    did: str | None = None


class SetDefaultDownloaderRequest(BaseModel):
    did: str | None = None


class SetDefaultDownloadSettingRequest(BaseModel):
    sid: str | None = None


class GetRemoveTorrentsRequest(BaseModel):
    tid: str | None = None


class GetTorrentRemoveTaskRequest(BaseModel):
    tid: str | None = None


class PtInfoRequest(BaseModel):
    ids: str | None = None


class PtIdRequest(BaseModel):
    id: str | None = None


class TestDownloaderRequest(BaseModel):
    type: str | None = None
    config: str | None = None


class UpdateDownloadSettingRequest(BaseModel):
    sid: str | int | None = None
    name: str | None = None
    category: str | None = None
    tags: str | None = None
    is_paused: int | bool | None = None
    upload_limit: int | str | None = 0
    download_limit: int | str | None = 0
    ratio_limit: int | str | None = 0
    seeding_time_limit: int | str | None = 0
    downloader: str | None = None


class UpdateDownloaderRequest(BaseModel):
    did: str | None = None
    name: str | None = None
    type: str | None = None
    enabled: int | None = None
    transfer: int | None = None
    only_nastool: int | None = None
    match_path: int | None = None
    rmt_mode: str | None = None
    config: str | None = None
    download_dir: str | None = None


class UpdateTorrentRemoveTaskRequest(BaseModel):
    data: dict


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/torrent-remove-tasks/run")
def auto_remove_torrents(
    req: AutoRemoveTorrentsRequest,
    user: str = Depends(require_permission("download:manage")),
    svc: DownloadService = Depends(get_download_service),
):
    svc.auto_remove_torrents(taskids=req.tid)
    return success()


@router.post("/downloaders/check")
def check_downloader(
    req: CheckDownloaderRequest,
    user: str = Depends(require_permission("download:manage")),
    svc: Downloader = Depends(get_downloader_service),
):
    did = req.did
    if not did:
        return fail()
    checked = req.checked
    flag = req.flag
    enabled = transfer = only_nastool = match_path = None
    if flag == "enabled":
        enabled = 1 if checked else 0
    elif flag == "transfer":
        transfer = 1 if checked else 0
    elif flag == "only_nastool":
        only_nastool = 1 if checked else 0
    elif flag == "match_path":
        match_path = 1 if checked else 0
    svc.check_downloader(did=did, enabled=enabled, transfer=transfer, only_nastool=only_nastool, match_path=match_path)
    return success()


@router.post("/downloaders/delete")
def del_downloader(
    req: DelDownloaderRequest,
    user: str = Depends(require_permission("download:manage")),
    svc: Downloader = Depends(get_downloader_service),
):
    svc.delete_downloader(did=req.did)
    return success()


@router.post("/settings/delete")
def delete_download_setting(
    req: DeleteDownloadSettingRequest,
    user: str = Depends(require_permission("download:manage")),
    svc: Downloader = Depends(get_downloader_service),
):
    svc.delete_download_setting(sid=req.sid)
    return success()


@router.post("/torrent-remove-tasks/delete")
def delete_torrent_remove_task(
    req: DeleteTorrentRemoveTaskRequest,
    user: str = Depends(require_permission("download:manage")),
    svc: DownloadService = Depends(get_download_service),
):
    flag = svc.delete_torrent_remove_task(taskid=req.tid)
    if flag:
        return success()
    return fail()


@router.post("/tasks/add")
def download(
    req: DownloadRequest,
    user: UserContext = Depends(require_permission("download:manage")),
    svc: DownloadService = Depends(get_download_service),
):
    def _do_download():
        try:
            svc.download_from_search_results(
                dl_id=req.id, dl_dir=req.dir, dl_setting=req.setting, user_name=user.nickname or user.username
            )
        except Exception as e:
            ExceptionUtils.exception_traceback(e)

    ThreadHelper().start_thread(_do_download, ())
    return success(msg="下载任务已提交")


@router.post("/tasks/add_link")
def download_link(
    req: DownloadLinkRequest,
    user: UserContext = Depends(require_permission("download:manage")),
    svc: DownloadService = Depends(get_download_service),
):
    def _do_download():
        try:
            svc.download_from_link(
                site=req.site,
                enclosure=req.enclosure,
                title=req.title,
                description=req.description,
                page_url=req.page_url,
                size=req.size,
                seeders=req.seeders,
                uploadvolumefactor=req.uploadvolumefactor,
                downloadvolumefactor=req.downloadvolumefactor,
                dl_dir=req.dl_dir,
                dl_setting=req.dl_setting,
                user_name=user.nickname or user.username,
            )
        except Exception as e:
            ExceptionUtils.exception_traceback(e)

    ThreadHelper().start_thread(_do_download, ())
    return success(msg="下载任务已提交")


@router.post("/tasks/resolve_url")
def resolve_download_url(
    req: ResolveDownloadUrlRequest,
    user: str = Depends(require_any_permission("download:view", "download:manage")),
    svc: DownloadService = Depends(get_download_service),
):
    url = svc.resolve_download_url(page_url=req.page_url or "", enclosure=req.enclosure)
    if not url:
        return fail(msg="无法获取下载链接")
    return success(data={"url": url})


@router.post("/tasks/add_torrent")
def download_torrent(
    req: DownloadTorrentRequest,
    user: UserContext = Depends(require_permission("download:manage")),
    svc: DownloadService = Depends(get_download_service),
):
    # 快速校验
    if not req.urls and not req.files:
        return fail(msg="没有种子文件或者种子链接")

    # 后台线程执行下载（避免网络 IO 阻塞 API 响应）
    def _do_download():
        try:
            svc.download_from_torrent_files_or_urls(
                files=req.files or [],
                urls=req.urls or [],
                dl_dir=req.dl_dir,
                dl_setting=req.dl_setting,
                user_name=user.nickname or user.username,
                page_url=req.page_url,
                upload_volume_factor=req.upload_volume_factor,
                download_volume_factor=req.download_volume_factor,
                title=req.title,
                description=req.description,
                site=req.site,
                size=req.size,
            )
        except Exception as e:
            ExceptionUtils.exception_traceback(e)

    ThreadHelper().start_thread(_do_download, ())
    return success(msg="下载任务已提交")


@router.post("/tools/hardlinks")
def find_hardlinks(
    req: FindHardlinksRequest,
    user: str = Depends(require_any_permission("download:view", "download:manage")),
):
    files = req.files
    file_dir = req.dir
    if not files:
        return []
    if not file_dir and os.name != "nt":
        file_dir = os.path.commonpath(files).replace("\\", "/")
        if file_dir != "/":
            file_dir = "/" + str(file_dir).split("/")[1]
        else:
            return []
    hardlinks = {}
    if files:
        try:
            for file in files:
                hardlinks[os.path.basename(file)] = SystemUtils().find_hardlinks(file=file, fdir=file_dir)
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return fail()
    return success(data=hardlinks)


@router.post("/downloaders/dirs")
def get_download_dirs(
    req: GetDownloadDirsRequest,
    user: str = Depends(require_any_permission("download:view", "download:manage")),
    site_svc: SiteService = Depends(get_site_service),
    downloader_svc: Downloader = Depends(get_downloader_service),
):
    sid = req.sid
    site = req.site
    if not sid and site:
        sid = site_svc.get_site_download_setting(site_name=site)
    dirs = downloader_svc.get_download_dirs(setting=sid)
    return success(data=dirs)


@router.post("/settings")
def get_download_setting(
    req: GetDownloadSettingRequest,
    user: str = Depends(require_any_permission("download:view", "download:manage")),
    svc: Downloader = Depends(get_downloader_service),
):
    sid = req.sid
    if sid:
        download_setting = svc.get_download_setting(sid=sid)
    else:
        download_setting = list(svc.get_download_setting().values())
    return success(data=download_setting)


@router.post("/downloaders")
def get_downloaders(
    req: GetDownloadersRequest,
    user: str = Depends(require_any_permission("download:view", "download:manage")),
    svc: Downloader = Depends(get_downloader_service),
):
    return success(data=svc.get_downloader_conf(did=req.did))


@router.post("/downloaders/default")
def set_default_downloader(
    req: SetDefaultDownloaderRequest,
    user: str = Depends(require_permission("download:manage")),
    svc: Downloader = Depends(get_downloader_service),
):
    """设置默认下载器"""
    if not req.did:
        return fail(msg="下载器ID不能为空")
    if svc.set_default_downloader_id(req.did):
        return success()
    return fail(msg="设置失败，下载器不存在")


@router.post("/downloaders/types")
def get_downloader_types(
    user: str = Depends(require_any_permission("download:view", "download:manage")),
):
    """获取支持的下载器类型配置"""
    return success(data=ModuleConf.DOWNLOADER_CONF)


@router.post("/indexers/statistics")
def get_indexer_statistics(
    req: EmptyRequest = EmptyRequest(),
    user: str = Depends(require_any_permission("download:view", "download:manage")),
    svc: DownloadService = Depends(get_download_service),
):
    stats, dataset = svc.get_indexer_statistics()
    return success(
        data={
            "stats": [
                {"name": s.name, "total": s.total, "fail": s.fail, "success": s.success, "avg": s.avg} for s in stats
            ],
            "dataset": dataset,
        }
    )


@router.post("/indexers")
def get_indexers(
    req: EmptyRequest = EmptyRequest(),
    user: str = Depends(require_any_permission("download:view", "download:manage")),
    svc: IndexerService = Depends(get_indexer_service),
):
    indexers = svc.get_user_indexers()
    return success(data=[{"id": i.id, "name": i.name} for i in indexers])


@router.post("/torrent-remove-tasks/candidates")
def get_remove_torrents(
    req: GetRemoveTorrentsRequest,
    user: str = Depends(require_any_permission("download:view", "download:manage")),
    svc: DownloadService = Depends(get_download_service),
):
    flag, torrents = svc.get_remove_torrents(taskid=req.tid)
    if not flag or not torrents:
        return fail(msg="未获取到符合处理条件种子")
    return success(data=torrents)


@router.post("/torrent-remove-tasks")
def get_torrent_remove_task(
    req: GetTorrentRemoveTaskRequest,
    user: str = Depends(require_any_permission("download:view", "download:manage")),
    svc: DownloadService = Depends(get_download_service),
):
    return success(data=svc.get_torrent_remove_tasks(taskid=req.tid))


@router.post("/tasks/info")
def pt_info(
    req: PtInfoRequest,
    user: str = Depends(require_any_permission("download:view", "download:manage")),
    svc: Downloader = Depends(get_downloader_service),
):
    torrents = svc.get_downloading_progress(ids=req.ids)
    return success(data=torrents)


@router.post("/tasks/remove")
def pt_remove(
    req: PtIdRequest,
    user: str = Depends(require_any_permission("download:view", "download:manage")),
    svc: Downloader = Depends(get_downloader_service),
):
    tid = req.id
    if tid:
        svc.delete_torrents(ids=tid, delete_file=True)
    return success(data=tid)


@router.post("/tasks/start")
def pt_start(
    req: PtIdRequest,
    user: str = Depends(require_permission("download:manage")),
    svc: Downloader = Depends(get_downloader_service),
):
    tid = req.id
    if tid:
        svc.start_torrents(ids=tid)
    return success(data=tid)


@router.post("/tasks/stop")
def pt_stop(
    req: PtIdRequest,
    user: str = Depends(require_permission("download:manage")),
    svc: Downloader = Depends(get_downloader_service),
):
    tid = req.id
    if tid:
        svc.stop_torrents(ids=tid)
    return success(data=tid)


@router.post("/downloaders/test")
def test_downloader(
    req: TestDownloaderRequest,
    user: str = Depends(require_permission("download:manage")),
    svc: Downloader = Depends(get_downloader_service),
):
    config = json.loads(req.config) if req.config else {}
    try:
        res = svc.get_status(dtype=req.type, config=config)
        if res:
            return success(data={"success": True, "message": "连接成功"})
        return success(data={"success": False, "message": "连接失败，请检查地址、端口及认证信息"})
    except Exception as e:
        return success(data={"success": False, "message": f"连接异常：{str(e)}"})


@router.post("/settings/update")
def update_download_setting(
    req: UpdateDownloadSettingRequest,
    user: str = Depends(require_permission("download:manage")),
    svc: Downloader = Depends(get_downloader_service),
):
    svc.update_download_setting(
        sid=req.sid,
        name=req.name,
        category=req.category,
        tags=req.tags,
        is_paused=req.is_paused,
        upload_limit=req.upload_limit or 0,
        download_limit=req.download_limit or 0,
        ratio_limit=req.ratio_limit or 0,
        seeding_time_limit=req.seeding_time_limit or 0,
        downloader=req.downloader,
    )
    return success()


@router.post("/settings/default")
def set_default_download_setting(
    req: SetDefaultDownloadSettingRequest,
    user: str = Depends(require_permission("download:manage")),
    svc: Downloader = Depends(get_downloader_service),
):
    """设置默认下载设置"""
    if not req.sid:
        return fail(msg="下载设置ID不能为空")
    if svc.set_default_download_setting_id(req.sid):
        return success()
    return fail(msg="设置失败")


@router.post("/downloaders/update")
def update_downloader(
    req: UpdateDownloaderRequest,
    user: str = Depends(require_permission("download:manage")),
    svc: Downloader = Depends(get_downloader_service),
):
    did = req.did
    name = req.name
    dtype = req.type
    enabled = req.enabled
    transfer = req.transfer
    only_nastool = req.only_nastool
    match_path = req.match_path
    rmt_mode = req.rmt_mode
    config = req.config
    if config and not isinstance(config, str):
        config = json.dumps(config)
    download_dir = req.download_dir
    if download_dir and not isinstance(download_dir, str):
        download_dir = json.dumps(download_dir)
    svc.update_downloader(
        did=did,
        name=name,
        dtype=dtype,
        enabled=enabled,
        transfer=transfer,
        only_nastool=only_nastool,
        match_path=match_path,
        rmt_mode=rmt_mode,
        config=config,
        download_dir=download_dir,
    )
    return success()


@router.post("/torrent-remove-tasks/save")
def update_torrent_remove_task(
    req: UpdateTorrentRemoveTaskRequest,
    user: str = Depends(require_permission("download:manage")),
    svc: DownloadService = Depends(get_download_service),
):
    flag, msg = svc.update_torrent_remove_task(data=req.data)
    if not flag:
        return fail(msg=msg)
    return success()


@router.post("/tasks")
def get_downloading(
    req: EmptyRequest = EmptyRequest(),
    user: str = Depends(require_any_permission("download:view", "download:manage")),
    svc: DownloadService = Depends(get_download_service),
):
    torrents = svc.get_downloading_with_media_info()
    return success(data=torrents)


@router.post("/tools/blacklist/clear")
def truncate_blacklist(
    req: EmptyRequest = EmptyRequest(),
    user: str = Depends(require_permission("download:manage")),
    svc: FileTransfer = Depends(get_filetransfer_service),
):
    svc.truncate_transfer_blacklist()
    return success()

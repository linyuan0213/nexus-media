"""
Brush Router — FastAPI 迁移
对应原 web/controllers/brush.py，复用 app/services/brush_service.py
"""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_current_user, get_brush_service
from app.utils.response import success, fail
from app.services.brush_service import BrushService
from app.utils import ExceptionUtils

router = APIRouter()


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------

class EmptyRequest(BaseModel):
    data: Optional[dict] = None


class AddBrushTaskRequest(BaseModel):
    brushtask_id: Optional[int] = None
    brushtask_name: Optional[str] = None
    brushtask_site: Optional[str] = None
    brushtask_free: Optional[str] = None
    brushtask_rssurl: Optional[str] = None
    brushtask_interval: Optional[int] = None
    brushtask_downloader: Optional[str] = None
    brushtask_totalsize: Optional[str] = None
    brushtask_time_range: Optional[str] = None
    brushtask_label: Optional[str] = None
    brushtask_savepath: Optional[str] = None
    brushtask_transfer: Optional[int] = None
    brushtask_state: Optional[str] = None
    brushtask_sendmessage: Optional[int] = None
    brushtask_hr: Optional[str] = None
    brushtask_torrent_size: Optional[str] = None
    brushtask_include: Optional[str] = None
    brushtask_exclude: Optional[str] = None
    brushtask_dlcount: Optional[str] = None
    brushtask_peercount: Optional[str] = None
    brushtask_pubdate: Optional[str] = None
    brushtask_upspeed: Optional[str] = None
    brushtask_downspeed: Optional[str] = None
    brushtask_exclude_subscribe: Optional[str] = None
    brushtask_mode: Optional[str] = None
    brushtask_seedtime: Optional[str] = None
    brushtask_hr_seedtime: Optional[str] = None
    brushtask_seedratio: Optional[str] = None
    brushtask_seedsize: Optional[str] = None
    brushtask_dltime: Optional[str] = None
    brushtask_avg_upspeed: Optional[str] = None
    brushtask_iatime: Optional[str] = None
    brushtask_pending_time: Optional[str] = None
    brushtask_freespace: Optional[str] = None
    brushtask_freestatus: Optional[str] = None
    brushtask_stopfree: Optional[int] = None


class BrushTaskIdRequest(BaseModel):
    id: Optional[int] = None


class UpdateBrushTaskStateRequest(BaseModel):
    state: Optional[str] = None
    ids: Optional[list] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/add_brushtask")
def add_brushtask(
    req: AddBrushTaskRequest,
    user: str = Depends(get_current_user),
    svc: BrushService = Depends(get_brush_service),
):
    svc.add_or_update_task(req.model_dump())
    return success()


@router.post("/brushtask_detail")
def brushtask_detail(
    req: BrushTaskIdRequest,
    user: str = Depends(get_current_user),
    svc: BrushService = Depends(get_brush_service),
):
    dto = svc.get_task(req.id)
    if not dto.task:
        return fail(task={})
    return success(task=dto.task)


@router.post("/list_brushtasks")
def list_brushtasks(
    req: EmptyRequest = EmptyRequest(),
    user: str = Depends(get_current_user),
    svc: BrushService = Depends(get_brush_service),
):
    return success(tasks=svc.get_tasks())


@router.post("/del_brushtask")
def del_brushtask(
    req: BrushTaskIdRequest,
    user: str = Depends(get_current_user),
    svc: BrushService = Depends(get_brush_service),
):
    brush_id = req.id
    if brush_id:
        svc.delete_task(brush_id)
        return success()
    return fail()


@router.post("/list_brushtask_torrents")
def list_brushtask_torrents(
    req: BrushTaskIdRequest,
    user: str = Depends(get_current_user),
    svc: BrushService = Depends(get_brush_service),
):
    dto = svc.get_torrents(req.id)
    if not dto.torrents:
        return fail(msg="未下载种子或未获取到种子明细")
    return success(data=dto.torrents)


@router.post("/run_brushtask")
def run_brushtask(
    req: BrushTaskIdRequest,
    user: str = Depends(get_current_user),
    svc: BrushService = Depends(get_brush_service),
):
    svc.run_task(req.id)
    return success()


@router.post("/update_brushtask_state")
def update_brushtask_state(
    req: UpdateBrushTaskStateRequest,
    user: str = Depends(get_current_user),
    svc: BrushService = Depends(get_brush_service),
):
    try:
        svc.update_task_state(
            state=req.state,
            task_ids=req.ids
        )
        return success(msg="")
    except Exception as e:
        ExceptionUtils.exception_traceback(e)
        return fail(msg="刷流任务设置失败")

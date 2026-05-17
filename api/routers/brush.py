"""
Brush Router — FastAPI 迁移
对应原 web/controllers/brush.py，复用 app/services/brush_service.py
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_brush_service, require_any_permission, require_permission
from app.services.brush_service import BrushService
from app.utils import ExceptionUtils
from app.utils.response import fail, success

router = APIRouter()


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------


class EmptyRequest(BaseModel):
    data: dict | None = None


class AddBrushTaskRequest(BaseModel):
    brushtask_id: int | None = None
    brushtask_name: str | None = None
    brushtask_site: str | None = None
    brushtask_free: str | None = None
    brushtask_rssurl: str | None = None
    brushtask_interval: int | None = None
    brushtask_downloader: str | None = None
    brushtask_totalsize: str | None = None
    brushtask_time_range: str | None = None
    brushtask_label: str | None = None
    brushtask_savepath: str | None = None
    brushtask_transfer: int | None = None
    brushtask_state: str | None = None
    brushtask_sendmessage: int | None = None
    brushtask_rule_id: int | None = None
    brushtask_hr: str | None = None
    brushtask_torrent_size: str | None = None
    brushtask_include: str | None = None
    brushtask_exclude: str | None = None
    brushtask_dlcount: str | None = None
    brushtask_peercount: str | None = None
    brushtask_pubdate: str | None = None
    brushtask_upspeed: str | None = None
    brushtask_downspeed: str | None = None
    brushtask_exclude_subscribe: str | bool | None = None
    brushtask_mode: str | None = None
    brushtask_seedtime: str | None = None
    brushtask_hr_seedtime: str | None = None
    brushtask_seedratio: str | None = None
    brushtask_seedsize: str | None = None
    brushtask_dltime: str | None = None
    brushtask_avg_upspeed: str | None = None
    brushtask_iatime: str | None = None
    brushtask_pending_time: str | None = None
    brushtask_freespace: str | None = None
    brushtask_freestatus: str | bool | None = None
    brushtask_stopfree: int | None = None


class BrushTaskIdRequest(BaseModel):
    id: int | None = None


class UpdateBrushTaskStateRequest(BaseModel):
    state: str | None = None
    ids: list | None = None


class BrushRuleIdRequest(BaseModel):
    id: int | None = None


class SaveBrushRuleRequest(BaseModel):
    id: int | None = None
    name: str | None = None
    rss_rule: dict | None = None
    remove_rule: dict | None = None
    stop_rule: dict | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/tasks/add")
def add_brushtask(
    req: AddBrushTaskRequest,
    _: None = Depends(require_permission("brush:manage")),
    svc: BrushService = Depends(get_brush_service),
):
    svc.add_or_update_task(req.model_dump())
    return success()


@router.post("/tasks/update")
def update_brushtask(
    req: AddBrushTaskRequest,
    _: None = Depends(require_permission("brush:manage")),
    svc: BrushService = Depends(get_brush_service),
):
    svc.add_or_update_task(req.model_dump())
    return success()


@router.post("/tasks/detail")
def brushtask_detail(
    req: BrushTaskIdRequest,
    _: None = Depends(require_any_permission("brush:view", "brush:manage")),
    svc: BrushService = Depends(get_brush_service),
):
    dto = svc.get_task(req.id)
    if not dto.task:
        return fail(data={"task": {}})
    return success(data={"task": dto.task})


@router.post("/tasks")
def list_brushtasks(
    req: EmptyRequest = EmptyRequest(),
    _: None = Depends(require_any_permission("brush:view", "brush:manage")),
    svc: BrushService = Depends(get_brush_service),
):
    return success(data=svc.get_tasks())


@router.post("/tasks/delete")
def del_brushtask(
    req: BrushTaskIdRequest,
    _: None = Depends(require_permission("brush:manage")),
    svc: BrushService = Depends(get_brush_service),
):
    brush_id = req.id
    if brush_id:
        svc.delete_task(brush_id)
        return success()
    return fail()


@router.post("/tasks/torrents")
def list_brushtask_torrents(
    req: BrushTaskIdRequest,
    _: None = Depends(require_any_permission("brush:view", "brush:manage")),
    svc: BrushService = Depends(get_brush_service),
):
    dto = svc.get_torrents(req.id)
    if not dto.torrents:
        return success(data={"list": []})
    return success(data={"list": dto.torrents})


@router.post("/tasks/run")
def run_brushtask(
    req: BrushTaskIdRequest,
    _: None = Depends(require_permission("brush:manage")),
    svc: BrushService = Depends(get_brush_service),
):
    svc.run_task(req.id)
    return success()


@router.post("/tasks/state")
def update_brushtask_state(
    req: UpdateBrushTaskStateRequest,
    _: None = Depends(require_permission("brush:manage")),
    svc: BrushService = Depends(get_brush_service),
):
    try:
        svc.update_task_state(state=req.state, task_ids=req.ids)
        return success(msg="")
    except Exception as e:
        ExceptionUtils.exception_traceback(e)
        return fail(msg="刷流任务设置失败")


# ---------------------------------------------------------------------------
# Brush Rule Endpoints
# ---------------------------------------------------------------------------


@router.post("/rules")
def list_brush_rules(
    req: EmptyRequest = EmptyRequest(),
    _: None = Depends(require_any_permission("brush:view", "brush:manage")),
    svc: BrushService = Depends(get_brush_service),
):
    return success(data=svc.get_rules())


@router.post("/rules/detail")
def brush_rule_detail(
    req: BrushRuleIdRequest,
    _: None = Depends(require_any_permission("brush:view", "brush:manage")),
    svc: BrushService = Depends(get_brush_service),
):
    data = svc.get_rule(req.id or 0)
    if not data:
        return fail(msg="规则不存在")
    return success(data=data)


@router.post("/rules/save")
def save_brush_rule(
    req: SaveBrushRuleRequest,
    _: None = Depends(require_permission("brush:manage")),
    svc: BrushService = Depends(get_brush_service),
):
    if not req.name:
        return fail(msg="规则名称不能为空")
    if req.id:
        svc.update_rule(req.id, req.model_dump())
        return success(msg="规则已更新")
    rid = svc.add_rule(req.model_dump())
    return success(data={"id": rid}, msg="规则已创建")


@router.post("/rules/delete")
def delete_brush_rule(
    req: BrushRuleIdRequest,
    _: None = Depends(require_permission("brush:manage")),
    svc: BrushService = Depends(get_brush_service),
):
    if req.id:
        svc.delete_rule(req.id)
        return success()
    return fail(msg="规则ID不能为空")

"""
Scheduler Router — FastAPI 迁移
对应原 web/controllers/scheduler.py，复用 app/services/scheduler_service.py
"""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_scheduler_service, require_any_permission, require_permission
from app.utils.response import success, fail
from app.schemas.scheduler import (
    DeleteSchedulerJobRequest,
    PauseSchedulerJobRequest,
    ResumeSchedulerJobRequest,
    RunSchedulerJobRequest,
    UpdateSchedulerJobRequest,
)
from app.services.scheduler_service import SchedulerService

router = APIRouter()


# ---------------------------------------------------------------------------
# Request Models (兼容前端原始字段名)
# ---------------------------------------------------------------------------

class EmptyRequest(BaseModel):
    data: Optional[dict] = None


class JobIdRequest(BaseModel):
    id: Optional[str] = None


class UpdateJobRequest(BaseModel):
    id: Optional[str] = None
    trigger: Optional[str] = None
    seconds: Optional[int] = None
    minutes: Optional[int] = None
    hours: Optional[int] = None
    cron: Optional[str] = None
    run_date: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/jobs/delete")
def delete_scheduler_job(
    req: JobIdRequest,
    _: None = Depends(require_permission("service:manage")),
    svc: SchedulerService = Depends(get_scheduler_service),
):
    job_id = req.id or ""
    if not job_id:
        return fail(msg="任务ID不能为空")
    resp = svc.delete_job(DeleteSchedulerJobRequest(id=job_id))
    if resp.code == 0:
        return success(msg=resp.msg)
    return fail(msg=resp.msg)


@router.post("/jobs")
def get_scheduler_jobs(
    req: EmptyRequest = EmptyRequest(),
    _: None = Depends(require_any_permission("service:view", "service:manage")),
    svc: SchedulerService = Depends(get_scheduler_service),
):
    resp = svc.get_jobs()
    if resp.code != 0:
        return fail(msg="调度器未启动")
    return success(data=[job.model_dump() for job in resp.data])


@router.post("/jobs/pause")
def pause_scheduler_job(
    req: JobIdRequest,
    _: None = Depends(require_permission("service:manage")),
    svc: SchedulerService = Depends(get_scheduler_service),
):
    job_id = req.id or ""
    if not job_id:
        return fail(msg="任务ID不能为空")
    resp = svc.pause_job(PauseSchedulerJobRequest(id=job_id))
    if resp.code == 0:
        return success(msg=resp.msg)
    return fail(msg=resp.msg)


@router.post("/jobs/resume")
def resume_scheduler_job(
    req: JobIdRequest,
    _: None = Depends(require_permission("service:manage")),
    svc: SchedulerService = Depends(get_scheduler_service),
):
    job_id = req.id or ""
    if not job_id:
        return fail(msg="任务ID不能为空")
    resp = svc.resume_job(ResumeSchedulerJobRequest(id=job_id))
    if resp.code == 0:
        return success(msg=resp.msg)
    return fail(msg=resp.msg)


@router.post("/jobs/run")
def run_scheduler_job(
    req: JobIdRequest,
    _: None = Depends(require_permission("service:manage")),
    svc: SchedulerService = Depends(get_scheduler_service),
):
    job_id = req.id or ""
    if not job_id:
        return fail(msg="任务ID不能为空")
    resp = svc.run_job(RunSchedulerJobRequest(id=job_id))
    if resp.code == 0:
        return success(msg=resp.msg)
    return fail(msg=resp.msg)


@router.post("/jobs/update")
def update_scheduler_job(
    req: UpdateJobRequest,
    _: None = Depends(require_permission("service:manage")),
    svc: SchedulerService = Depends(get_scheduler_service),
):
    job_id = req.id or ""
    if not job_id:
        return fail(msg="任务ID不能为空")
    try:
        dto = UpdateSchedulerJobRequest(
            id=job_id,
            trigger=req.trigger or "",
            seconds=req.seconds,
            minutes=req.minutes,
            hours=req.hours,
            cron=req.cron,
            run_date=req.run_date,
        )
    except Exception as e:
        return fail(code=1, msg=str(e))
    resp = svc.update_job(dto)
    if resp.code == 0:
        return success(msg=resp.msg)
    return fail(msg=resp.msg)

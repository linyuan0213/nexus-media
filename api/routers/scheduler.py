"""
Scheduler Router — FastAPI 迁移
对应原 web/controllers/scheduler.py，复用 app/services/scheduler_service.py
"""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_current_user, get_scheduler_service
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

@router.post("/delete_scheduler_job")
def delete_scheduler_job(
    req: JobIdRequest,
    user: str = Depends(get_current_user),
    svc: SchedulerService = Depends(get_scheduler_service),
):
    job_id = req.id or ""
    if not job_id:
        return fail(msg="任务ID不能为空")
    resp = svc.delete_job(DeleteSchedulerJobRequest(id=job_id))
    if resp.code == 0:
        return success(msg=resp.msg)
    return fail(msg=resp.msg)


@router.post("/get_scheduler_jobs")
def get_scheduler_jobs(
    req: EmptyRequest = EmptyRequest(),
    user: str = Depends(get_current_user),
    svc: SchedulerService = Depends(get_scheduler_service),
):
    resp = svc.get_jobs()
    if resp.code != 0:
        return fail(msg="调度器未启动")
    return success(data=[job.model_dump() for job in resp.data])


@router.post("/pause_scheduler_job")
def pause_scheduler_job(
    req: JobIdRequest,
    user: str = Depends(get_current_user),
    svc: SchedulerService = Depends(get_scheduler_service),
):
    job_id = req.id or ""
    if not job_id:
        return fail(msg="任务ID不能为空")
    resp = svc.pause_job(PauseSchedulerJobRequest(id=job_id))
    if resp.code == 0:
        return success(msg=resp.msg)
    return fail(msg=resp.msg)


@router.post("/resume_scheduler_job")
def resume_scheduler_job(
    req: JobIdRequest,
    user: str = Depends(get_current_user),
    svc: SchedulerService = Depends(get_scheduler_service),
):
    job_id = req.id or ""
    if not job_id:
        return fail(msg="任务ID不能为空")
    resp = svc.resume_job(ResumeSchedulerJobRequest(id=job_id))
    if resp.code == 0:
        return success(msg=resp.msg)
    return fail(msg=resp.msg)


@router.post("/run_scheduler_job")
def run_scheduler_job(
    req: JobIdRequest,
    user: str = Depends(get_current_user),
    svc: SchedulerService = Depends(get_scheduler_service),
):
    job_id = req.id or ""
    if not job_id:
        return fail(msg="任务ID不能为空")
    resp = svc.run_job(RunSchedulerJobRequest(id=job_id))
    if resp.code == 0:
        return success(msg=resp.msg)
    return fail(msg=resp.msg)


@router.post("/update_scheduler_job")
def update_scheduler_job(
    req: UpdateJobRequest,
    user: str = Depends(get_current_user),
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

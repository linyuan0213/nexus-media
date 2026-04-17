from flask import Blueprint
from web.core.decorators import any_auth, parse_json_data
from web.core.response import success, fail
from pydantic import ValidationError

from app.schemas.scheduler import (
    DeleteSchedulerJobRequest,
    PauseSchedulerJobRequest,
    ResumeSchedulerJobRequest,
    RunSchedulerJobRequest,
    UpdateSchedulerJobRequest,
)
from app.services.scheduler_service import SchedulerService

scheduler_bp = Blueprint("scheduler", __name__, url_prefix="/api/web/scheduler")


def _safe_dto(cls, data, resp_fn):
    try:
        return cls(**data)
    except ValidationError as e:
        first = e.errors()[0]
        return resp_fn(code=1, msg=first.get("message", str(e)))


@scheduler_bp.route('/delete_scheduler_job', methods=['POST'])
@any_auth
@parse_json_data
def _delete_scheduler_job(data):
    req = DeleteSchedulerJobRequest(id=data.get("id") or "")
    if not req.id:
        return fail(msg="任务ID不能为空")
    resp = SchedulerService().delete_job(req)
    if resp.code == 0:
        return success(msg=resp.msg)
    return fail(msg=resp.msg)


@scheduler_bp.route('/get_scheduler_jobs', methods=['POST'])
@any_auth
@parse_json_data
def _get_scheduler_jobs(data):
    resp = SchedulerService().get_jobs()
    if resp.code != 0:
        return fail(msg="调度器未启动")
    return success(data=[job.model_dump() for job in resp.data])


@scheduler_bp.route('/pause_scheduler_job', methods=['POST'])
@any_auth
@parse_json_data
def _pause_scheduler_job(data):
    req = PauseSchedulerJobRequest(id=data.get("id") or "")
    if not req.id:
        return fail(msg="任务ID不能为空")
    resp = SchedulerService().pause_job(req)
    if resp.code == 0:
        return success(msg=resp.msg)
    return fail(msg=resp.msg)


@scheduler_bp.route('/resume_scheduler_job', methods=['POST'])
@any_auth
@parse_json_data
def _resume_scheduler_job(data):
    req = ResumeSchedulerJobRequest(id=data.get("id") or "")
    if not req.id:
        return fail(msg="任务ID不能为空")
    resp = SchedulerService().resume_job(req)
    if resp.code == 0:
        return success(msg=resp.msg)
    return fail(msg=resp.msg)


@scheduler_bp.route('/run_scheduler_job', methods=['POST'])
@any_auth
@parse_json_data
def _run_scheduler_job(data):
    req = RunSchedulerJobRequest(id=data.get("id") or "")
    if not req.id:
        return fail(msg="任务ID不能为空")
    resp = SchedulerService().run_job(req)
    if resp.code == 0:
        return success(msg=resp.msg)
    return fail(msg=resp.msg)


@scheduler_bp.route('/update_scheduler_job', methods=['POST'])
@any_auth
@parse_json_data
def _update_scheduler_job(data):
    try:
        req = UpdateSchedulerJobRequest(
            id=data.get("id") or "",
            trigger=data.get("trigger") or "",
            seconds=data.get("seconds"),
            minutes=data.get("minutes"),
            hours=data.get("hours"),
            cron=data.get("cron"),
            run_date=data.get("run_date"),
        )
    except ValidationError as e:
        first = e.errors()[0]
        return fail(code=1, msg=first.get("message", str(e)))
    if not req.id:
        return fail(msg="任务ID不能为空")
    resp = SchedulerService().update_job(req)
    if resp.code == 0:
        return success(msg=resp.msg)
    return fail(msg=resp.msg)

"""
调度器业务服务：脱离 Web 框架，可独立单元测试
"""
import time
from typing import Any, ClassVar, List, Optional

import log
from app.helper import ThreadHelper
from app.services.scheduler_core import SchedulerCore
from app.schemas.scheduler import (
    DeleteSchedulerJobRequest,
    DeleteSchedulerJobResponse,
    GetSchedulerJobsResponse,
    PauseSchedulerJobRequest,
    PauseSchedulerJobResponse,
    ResumeSchedulerJobRequest,
    ResumeSchedulerJobResponse,
    RunSchedulerJobRequest,
    RunSchedulerJobResponse,
    SchedulerJob,
    JobTrigger,
    UpdateSchedulerJobRequest,
    UpdateSchedulerJobResponse,
)


class SchedulerService:
    """调度器业务服务"""

    _UNSET: ClassVar[Any] = object()

    def __init__(self, scheduler: Optional[SchedulerCore] = _UNSET):
        self._scheduler = scheduler

    def _get_scheduler(self) -> Optional[SchedulerCore]:
        if self._scheduler is not self._UNSET:
            return self._scheduler
        core = SchedulerCore()
        return core if core.is_running else None

    def delete_job(self, req: DeleteSchedulerJobRequest) -> DeleteSchedulerJobResponse:
        svc = self._get_scheduler()
        if not svc:
            return DeleteSchedulerJobResponse(code=1, msg="调度器未启动")
        ret = svc.remove_job(req.id)
        if ret:
            return DeleteSchedulerJobResponse(code=0, msg="删除成功")
        return DeleteSchedulerJobResponse(code=1, msg="删除失败")

    def get_jobs(self) -> GetSchedulerJobsResponse:
        svc = self._get_scheduler()
        if not svc:
            return GetSchedulerJobsResponse(code=1)

        jobs = svc.get_jobs()
        stats = svc.get_job_statistics()
        job_list: List[SchedulerJob] = []
        for job in jobs:
            trigger_info = JobTrigger()
            trigger_type = "unknown"
            try:
                if hasattr(job.trigger, 'interval'):
                    trigger_type = "interval"
                    trigger_info = JobTrigger(
                        type="interval",
                        seconds=getattr(job.trigger, 'interval_length', None)
                    )
                elif hasattr(job.trigger, 'fields'):
                    trigger_type = "cron"
                    trigger_info = JobTrigger(
                        type="cron",
                        expression=str(job.trigger)
                    )
                elif hasattr(job.trigger, 'run_date'):
                    trigger_type = "date"
                    trigger_info = JobTrigger(
                        type="date",
                        run_date=job.trigger.run_date.isoformat() if job.trigger.run_date else None
                    )
                else:
                    trigger_info = JobTrigger(
                        type=getattr(job.trigger, '__class__.__name__', 'unknown'),
                        expression=str(job.trigger)
                    )
            except Exception:
                trigger_info = JobTrigger(type="unknown")

            job_list.append(SchedulerJob(
                id=job.id,
                name=job.name or job.id,
                next_run_time=job.next_run_time.isoformat() if job.next_run_time else None,
                trigger=trigger_info,
                trigger_type=trigger_type,
                args=[str(a) for a in (job.args or [])],
                kwargs=job.kwargs or {},
                jobstore=getattr(job, '_jobstore_alias', 'default'),
                paused=job.next_run_time is None,
                statistics=stats.get(job.id, {})
            ))

        job_list.sort(key=lambda x: x.id)
        return GetSchedulerJobsResponse(code=0, data=job_list)

    def pause_job(self, req: PauseSchedulerJobRequest) -> PauseSchedulerJobResponse:
        svc = self._get_scheduler()
        if not svc:
            return PauseSchedulerJobResponse(code=1, msg="调度器未启动")
        ret = svc.pause_job(req.id)
        if ret:
            return PauseSchedulerJobResponse(code=0, msg="暂停成功")
        return PauseSchedulerJobResponse(code=1, msg="暂停失败")

    def resume_job(self, req: ResumeSchedulerJobRequest) -> ResumeSchedulerJobResponse:
        svc = self._get_scheduler()
        if not svc:
            return ResumeSchedulerJobResponse(code=1, msg="调度器未启动")
        ret = svc.resume_job(req.id)
        if ret:
            return ResumeSchedulerJobResponse(code=0, msg="恢复成功")
        return ResumeSchedulerJobResponse(code=1, msg="恢复失败")

    def run_job(self, req: RunSchedulerJobRequest) -> RunSchedulerJobResponse:
        svc = self._get_scheduler()
        if not svc:
            return RunSchedulerJobResponse(code=1, msg="调度器未启动")

        job = svc.get_job(req.id)
        if not job:
            return RunSchedulerJobResponse(code=1, msg="任务不存在")

        def _wrapper():
            start = time.time()
            try:
                job.func(*(job.args or ()), **(job.kwargs or {}))
                duration = time.time() - start
                if svc:
                    svc._get_job_stats(req.id).record_success(duration)
                log.info(f"手动执行任务 {req.id} 成功, 耗时: {duration:.3f}s")
            except Exception as e:
                duration = time.time() - start
                if svc:
                    svc._get_job_stats(req.id).record_failure(str(e))
                log.error(f"立即执行任务 {req.id} 执行异常: {e}")

        ThreadHelper().start_thread(_wrapper, ())
        return RunSchedulerJobResponse(code=0, msg="任务已触发")

    def update_job(self, req: UpdateSchedulerJobRequest) -> UpdateSchedulerJobResponse:
        svc = self._get_scheduler()
        if not svc:
            return UpdateSchedulerJobResponse(code=1, msg="调度器未启动")

        job = svc.get_job(req.id)
        if not job:
            return UpdateSchedulerJobResponse(code=1, msg="任务不存在")

        try:
            if req.trigger == "interval":
                kwargs = {}
                for key in ["seconds", "minutes", "hours"]:
                    val = getattr(req, key)
                    if val is not None:
                        kwargs[key] = int(val)
                if not kwargs:
                    return UpdateSchedulerJobResponse(code=1, msg="interval 触发器缺少时间参数")
                svc.reschedule_job(req.id, trigger="interval", **kwargs)
            elif req.trigger == "cron":
                if not req.cron:
                    return UpdateSchedulerJobResponse(code=1, msg="cron 触发器缺少表达式")
                parts = req.cron.strip().split()
                if len(parts) != 5:
                    return UpdateSchedulerJobResponse(code=1, msg="cron 表达式格式错误")
                minute, hour, day, month, day_of_week = parts
                svc.reschedule_job(
                    req.id,
                    trigger="cron",
                    minute=minute,
                    hour=hour,
                    day=day,
                    month=month,
                    day_of_week=day_of_week
                )
            elif req.trigger == "date":
                from apscheduler.triggers.date import DateTrigger
                from dateutil import parser as date_parser
                if not req.run_date:
                    return UpdateSchedulerJobResponse(code=1, msg="date 触发器缺少执行时间")
                run_date = date_parser.parse(req.run_date)
                svc.reschedule_job(req.id, trigger=DateTrigger(run_date=run_date))
            else:
                return UpdateSchedulerJobResponse(code=1, msg="不支持的触发器类型")

            return UpdateSchedulerJobResponse(code=0, msg="修改成功")
        except Exception as e:
            log.error(f"修改调度任务 {req.id} 失败: {e}")
            return UpdateSchedulerJobResponse(code=1, msg=str(e))

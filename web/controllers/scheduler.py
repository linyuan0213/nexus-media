from flask import Blueprint
from web.core.decorators import any_auth, parse_json_data
from web.core.response import success, fail
import datetime
import time
from typing import Dict, Any, List, Optional
import log
from app.scheduler import Scheduler
from apscheduler.triggers.cron import CronTrigger
from app.helper import ThreadHelper

scheduler_bp = Blueprint("scheduler", __name__, url_prefix="/api/web/scheduler")

@scheduler_bp.route('/delete_scheduler_job', methods=['POST'])
@any_auth
@parse_json_data
def _delete_scheduler_job(data):
        job_id = data.get("id")
        if not job_id:
            return fail(msg="任务ID不能为空")
        scheduler = Scheduler().scheduler
        if not scheduler:
            return fail(msg="调度器未启动")
        ret = scheduler.remove_job(job_id)
        if ret:
            return success(msg="删除成功")
        return fail(msg="删除失败")

@scheduler_bp.route('/get_scheduler_jobs', methods=['POST'])
@any_auth
@parse_json_data
def _get_scheduler_jobs(data):
        """
        获取调度器中的任务列表
        """
        scheduler = Scheduler().scheduler
        if not scheduler:
            return fail(msg="调度器未启动")

        jobs = scheduler.get_jobs()
        job_list = []
        stats = scheduler.get_job_statistics()
        for job in jobs:
            trigger_info = {}
            trigger_type = "unknown"
            try:
                if hasattr(job.trigger, 'interval'):
                    trigger_type = "interval"
                    trigger_info = {
                        "type": "interval",
                        "seconds": getattr(job.trigger, 'interval_length', None)
                    }
                elif hasattr(job.trigger, 'fields'):
                    trigger_type = "cron"
                    fields = []
                    for field in getattr(job.trigger, 'fields', []):
                        fields.append(str(field))
                    trigger_info = {
                        "type": "cron",
                        "expression": str(job.trigger)
                    }
                elif hasattr(job.trigger, 'run_date'):
                    trigger_type = "date"
                    trigger_info = {
                        "type": "date",
                        "run_date": job.trigger.run_date.isoformat() if job.trigger.run_date else None
                    }
                else:
                    trigger_info = {
                        "type": getattr(job.trigger, '__class__.__name__', 'unknown'),
                        "expression": str(job.trigger)
                    }
            except Exception:
                trigger_info = {"type": "unknown"}

            job_info = {
                "id": job.id,
                "name": job.name or job.id,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": trigger_info,
                "trigger_type": trigger_type,
                "args": [str(a) for a in (job.args or [])],
                "kwargs": job.kwargs or {},
                "jobstore": getattr(job, '_jobstore_alias', 'default'),
                "paused": job.next_run_time is None,
                "statistics": stats.get(job.id, {})
            }
            job_list.append(job_info)

        job_list.sort(key=lambda x: x["id"])
        return success(data=job_list)

@scheduler_bp.route('/pause_scheduler_job', methods=['POST'])
@any_auth
@parse_json_data
def _pause_scheduler_job(data):
        job_id = data.get("id")
        if not job_id:
            return fail(msg="任务ID不能为空")
        scheduler = Scheduler().scheduler
        if not scheduler:
            return fail(msg="调度器未启动")
        ret = scheduler.pause_job(job_id)
        if ret:
            return success(msg="暂停成功")
        return fail(msg="暂停失败")

@scheduler_bp.route('/resume_scheduler_job', methods=['POST'])
@any_auth
@parse_json_data
def _resume_scheduler_job(data):
        job_id = data.get("id")
        if not job_id:
            return fail(msg="任务ID不能为空")
        scheduler = Scheduler().scheduler
        if not scheduler:
            return fail(msg="调度器未启动")
        ret = scheduler.resume_job(job_id)
        if ret:
            return success(msg="恢复成功")
        return fail(msg="恢复失败")

@scheduler_bp.route('/run_scheduler_job', methods=['POST'])
@any_auth
@parse_json_data
def _run_scheduler_job(data):
        """
        立即执行一次调度任务
        """
        job_id = data.get("id")
        if not job_id:
            return fail(msg="任务ID不能为空")

        scheduler = Scheduler().scheduler
        if not scheduler:
            return fail(msg="调度器未启动")

        job = scheduler.get_job(job_id)
        if not job:
            return fail(msg="任务不存在")

        try:
            def _wrapper():
                start = time.time()
                try:
                    job.func(*(job.args or ()), **(job.kwargs or {}))
                    duration = time.time() - start
                    svc = Scheduler().scheduler
                    if svc:
                        svc._get_job_stats(job_id).record_success(duration)
                    log.info(f"手动执行任务 {job_id} 成功, 耗时: {duration:.3f}s")
                except Exception as e:
                    duration = time.time() - start
                    svc = Scheduler().scheduler
                    if svc:
                        svc._get_job_stats(job_id).record_failure(str(e))
                    log.error(f"立即执行任务 {job_id} 执行异常: {e}")

            ThreadHelper().start_thread(_wrapper, ())
            return success(msg="任务已触发")
        except Exception as e:
            log.error(f"立即执行任务 {job_id} 失败: {e}")
            return fail(msg=str(e))

@scheduler_bp.route('/update_scheduler_job', methods=['POST'])
@any_auth
@parse_json_data
def _update_scheduler_job(data):
        """
        修改调度任务触发器
        data: {
            "id": "job_id",
            "trigger": "interval" | "cron" | "date",
            "seconds": 300,
            "minutes": 5,
            "hours": 1,
            "cron": "*/5 * * * *",
            "run_date": "2024-01-01T00:00:00"
        }
        """
        job_id = data.get("id")
        if not job_id:
            return fail(msg="任务ID不能为空")

        scheduler = Scheduler().scheduler
        if not scheduler:
            return fail(msg="调度器未启动")

        job = scheduler.get_job(job_id)
        if not job:
            return fail(msg="任务不存在")

        trigger_type = data.get("trigger")
        try:
            if trigger_type == "interval":
                kwargs = {}
                for key in ["seconds", "minutes", "hours"]:
                    val = data.get(key)
                    if val is not None:
                        kwargs[key] = int(val)
                if not kwargs:
                    return fail(msg="interval 类型需要设置 seconds/minutes/hours 至少一个")
                scheduler.modify_job(job_id, trigger='interval', **kwargs)
            elif trigger_type == "cron":
                cron = data.get("cron")
                if not cron:
                    return fail(msg="cron表达式不能为空")
                trigger = CronTrigger.from_crontab(str(cron))
                scheduler.modify_job(job_id, trigger=trigger)
            elif trigger_type == "date":
                run_date_str = data.get("run_date")
                if not run_date_str:
                    return fail(msg="执行时间不能为空")
                run_date = datetime.datetime.fromisoformat(run_date_str)
                scheduler.modify_job(job_id, trigger='date', run_date=run_date)
            else:
                return fail(msg=f"不支持的触发器类型: {trigger_type}")

            log.info(f"调度任务 {job_id} 已更新")
            return success(msg="修改成功")
        except Exception as e:
            log.error(f"修改调度任务 {job_id} 失败: {e}")
            return fail(msg=str(e))


"""Brush scheduler - 刷流任务调度器."""

import contextlib
from typing import Any

from app.core.exceptions import DomainError, RepositoryError, ServiceError
from app.services.scheduler_core import SchedulerCore


class BrushTaskScheduler:
    """
    刷流任务调度器（调度编排层）
    职责：统一与 SchedulerCore 交互，管理刷流任务的定时 job。
    """

    _jobstore = "brushtask"

    def __init__(self, scheduler: SchedulerCore):
        self._scheduler = scheduler

    def start_job(self, func: Any, name: str, args: tuple, job_id: str, trigger_type: str, trigger_args: dict) -> None:
        self._scheduler.start_job(
            {
                "func": func,
                "name": name,
                "args": args,
                "job_id": job_id,
                "trigger": trigger_type,
                "jobstore": self._jobstore,
                **trigger_args,
            }
        )

    def remove_job(self, job_id: str) -> None:
        with contextlib.suppress(Exception):
            self._scheduler.remove_job(job_id, jobstore=self._jobstore)

    def remove_all_jobs(self) -> None:
        try:
            self._scheduler.remove_all_jobs(jobstore=self._jobstore)
        except (ServiceError, RepositoryError, DomainError):
            raise
        except Exception as e:
            print(str(e))

"""Scheduler models."""

import datetime
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from apscheduler.triggers.cron import CronTrigger


class JobStatus(Enum):
    """任务执行状态"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class JobStats:
    """任务执行统计"""

    job_id: str
    total_runs: int = 0
    success_count: int = 0
    failure_count: int = 0
    retry_count: int = 0
    last_run_time: datetime.datetime | None = None
    last_duration: float | None = None
    avg_duration: float = 0.0
    last_error: str | None = None
    consecutive_failures: int = 0

    def record_success(self, duration: float) -> None:
        """记录成功执行"""
        self.total_runs += 1
        self.success_count += 1
        self.consecutive_failures = 0
        self.last_run_time = datetime.datetime.now()
        self.last_duration = duration
        self.avg_duration = (self.avg_duration * (self.total_runs - 1) + duration) / self.total_runs

    def record_failure(self, error: str) -> None:
        """记录执行失败"""
        self.total_runs += 1
        self.failure_count += 1
        self.consecutive_failures += 1
        self.last_run_time = datetime.datetime.now()
        self.last_error = error

    def record_retry(self) -> None:
        """记录重试"""
        self.retry_count += 1

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "job_id": self.job_id,
            "total_runs": self.total_runs,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "retry_count": self.retry_count,
            "last_run_time": self.last_run_time.isoformat() if self.last_run_time else None,
            "last_duration": self.last_duration,
            "avg_duration": round(self.avg_duration, 3),
            "last_error": self.last_error,
            "consecutive_failures": self.consecutive_failures,
        }


@dataclass
class TaskConfig:
    """任务配置数据类"""

    job_id: str
    func: Callable
    name: str | None = None
    trigger: str = "interval"
    args: tuple = field(default_factory=tuple)
    kwargs: dict[str, Any] = field(default_factory=dict)
    jobstore: str = "default"
    hours: int | None = None
    minutes: int | None = None
    seconds: int | None = None
    cron: str | None = None
    run_date: datetime.datetime | None = None
    next_run_time: Any | None = None
    max_instances: int = 1
    misfire_grace_time: int = 300
    coalesce: bool = True

    def validate(self) -> None:
        """验证任务配置"""
        if not self.job_id:
            raise ValueError("job_id 不能为空")
        if not callable(self.func):
            raise ValueError("func 必须是可调用的")
        if self.trigger not in ("interval", "date", "cron"):
            raise ValueError(f"不支持的 trigger 类型: {self.trigger}")
        if self.trigger == "interval" and not any([self.hours, self.minutes, self.seconds]):
            raise ValueError("interval 类型任务需要设置 hours/minutes/seconds 至少一个")
        if self.trigger == "date" and not self.run_date:
            raise ValueError("date 类型任务需要设置 run_date")
        if self.trigger == "cron" and not self.cron:
            raise ValueError("cron 类型任务需要设置 cron 表达式")

    def to_scheduler_args(self) -> dict[str, Any]:
        """转换为 APScheduler 参数"""
        args = {
            "func": self.func,
            "args": self.args,
            "kwargs": self.kwargs,
            "id": self.job_id,
            "name": self.name,
            "jobstore": self.jobstore,
            "replace_existing": True,
            "max_instances": self.max_instances,
            "misfire_grace_time": self.misfire_grace_time,
            "coalesce": self.coalesce,
        }

        if self.trigger == "interval":
            trigger_args = {}
            if self.hours is not None:
                trigger_args["hours"] = self.hours
            if self.minutes is not None:
                trigger_args["minutes"] = self.minutes
            if self.seconds is not None:
                trigger_args["seconds"] = self.seconds
            args["trigger"] = "interval"
            args.update(trigger_args)
        elif self.trigger == "date":
            args["trigger"] = "date"
            args["run_date"] = self.run_date
        elif self.trigger == "cron":
            args["trigger"] = CronTrigger.from_crontab(self.cron)
        else:
            args["trigger"] = self.trigger

        if self.next_run_time is not None:
            args["next_run_time"] = self.next_run_time

        return args

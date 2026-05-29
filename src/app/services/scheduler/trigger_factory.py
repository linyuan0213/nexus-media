"""触发器工厂组件."""

import datetime
from collections.abc import Callable
from typing import Any

from apscheduler.job import Job

import log


class TriggerFactory:
    """触发器工厂组件"""

    def __init__(self, core):
        self._core = core

    def register_interval(
        self,
        job_id: str,
        func: Callable,
        seconds: int | None = None,
        minutes: int | None = None,
        hours: int | None = None,
        args: tuple | None = None,
        kwargs: dict[str, Any] | None = None,
        jobstore: str = "default",
        next_run_time: Any | None = None,
        max_instances: int = 1,
        misfire_grace_time: int = 300,
        coalesce: bool = True,
        name: str | None = None,
    ) -> Job | None:
        """注册 interval 类型定时任务（便捷方法）

        Args:
            job_id: 任务唯一标识
            func: 执行函数
            seconds: 间隔秒数
            minutes: 间隔分钟数
            hours: 间隔小时数
            args: 位置参数
            kwargs: 关键字参数
            jobstore: 存储位置
            next_run_time: 下次执行时间
            max_instances: 最大并发实例数
            misfire_grace_time: 错过执行的宽限时间
            coalesce: 是否合并错过的执行
            name: 任务名称

        Returns:
            Job 对象或 None
        """
        if not any([seconds, minutes, hours]):
            log.warn(f"register_interval: {job_id} 需要至少设置 seconds/minutes/hours 之一")
            return None
        return self._core._job_registry.start_job(
            {
                "job_id": job_id,
                "func": func,
                "name": name,
                "trigger": "interval",
                "args": args or (),
                "kwargs": kwargs or {},
                "jobstore": jobstore,
                "seconds": seconds,
                "minutes": minutes,
                "hours": hours,
                "next_run_time": next_run_time,
                "max_instances": max_instances,
                "misfire_grace_time": misfire_grace_time,
                "coalesce": coalesce,
            }
        )

    def register_date(
        self,
        job_id: str,
        func: Callable,
        run_date: datetime.datetime,
        args: tuple | None = None,
        kwargs: dict[str, Any] | None = None,
        jobstore: str = "default",
        max_instances: int = 1,
        misfire_grace_time: int = 60,
        coalesce: bool = True,
        name: str | None = None,
    ) -> Job | None:
        """注册 date 类型一次性定时任务（便捷方法）

        Args:
            job_id: 任务唯一标识
            func: 执行函数
            run_date: 执行时间
            args: 位置参数
            kwargs: 关键字参数
            jobstore: 存储位置
            max_instances: 最大并发实例数
            misfire_grace_time: 错过执行的宽限时间
            coalesce: 是否合并错过的执行
            name: 任务名称

        Returns:
            Job 对象或 None
        """
        return self._core._job_registry.start_job(
            {
                "job_id": job_id,
                "func": func,
                "name": name,
                "trigger": "date",
                "args": args or (),
                "kwargs": kwargs or {},
                "jobstore": jobstore,
                "run_date": run_date,
                "max_instances": max_instances,
                "misfire_grace_time": misfire_grace_time,
                "coalesce": coalesce,
            }
        )

    def register_cron(
        self,
        job_id: str,
        func: Callable,
        cron: str,
        args: tuple | None = None,
        kwargs: dict[str, Any] | None = None,
        jobstore: str = "default",
        next_run_time: Any | None = None,
        max_instances: int = 1,
        misfire_grace_time: int = 300,
        coalesce: bool = True,
        name: str | None = None,
    ) -> Job | None:
        """注册 cron 类型定时任务（便捷方法）

        Args:
            job_id: 任务唯一标识
            func: 执行函数
            cron: cron 表达式
            args: 位置参数
            kwargs: 关键字参数
            jobstore: 存储位置
            next_run_time: 下次执行时间
            max_instances: 最大并发实例数
            misfire_grace_time: 错过执行的宽限时间
            coalesce: 是否合并错过的执行
            name: 任务名称

        Returns:
            Job 对象或 None
        """
        return self._core._job_registry.start_job(
            {
                "job_id": job_id,
                "func": func,
                "name": name,
                "trigger": "cron",
                "args": args or (),
                "kwargs": kwargs or {},
                "jobstore": jobstore,
                "cron": cron,
                "next_run_time": next_run_time,
                "max_instances": max_instances,
                "misfire_grace_time": misfire_grace_time,
                "coalesce": coalesce,
            }
        )

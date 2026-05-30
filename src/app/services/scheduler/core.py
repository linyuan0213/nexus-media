"""SchedulerCore - 调度器核心服务."""

import contextlib
import datetime
import os
import threading
from collections.abc import Callable
from typing import Any

from apscheduler.events import (
    EVENT_JOB_ERROR,
    EVENT_JOB_EXECUTED,
    EVENT_JOB_MISSED,
    EVENT_JOB_SUBMITTED,
)
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.job import Job
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.background import BackgroundScheduler

import log
from app.core.exceptions import RepositoryError, ServiceError
from app.db.session import remove_session
from app.services.scheduler.cron_parser import CronParser
from app.services.scheduler.event_handler import EventHandler
from app.services.scheduler.job_registry import JobRegistry
from app.services.scheduler.models import JobStats, TaskConfig
from app.services.scheduler.retry_manager import RetryManager
from app.services.scheduler.stats_collector import StatsCollector
from app.services.scheduler.trigger_factory import TriggerFactory
from app.utils import ExceptionUtils


class SchedulerCore:
    """调度器核心服务

    提供任务调度、执行监控、失败重试、统计收集等功能。
    使用单例模式确保全局只有一个调度器实例。
    """

    # 默认 jobstore 配置
    DEFAULT_JOBSTORES = {
        "default": MemoryJobStore(),
        "brushtask": MemoryJobStore(),
        "rsscheck": MemoryJobStore(),
        "torrent_remove": MemoryJobStore(),
        "download": MemoryJobStore(),
        "plugin": MemoryJobStore(),
    }

    # 默认执行器配置
    DEFAULT_EXECUTORS = {"default": ThreadPoolExecutor(50)}

    # 默认任务默认配置
    DEFAULT_JOB_DEFAULTS = {"coalesce": True, "max_instances": 100, "misfire_grace_time": 300}

    # 最大重试次数
    MAX_RETRY_COUNT = 3

    # 重试延迟（秒）
    RETRY_DELAY = 60

    def __init__(self):
        self._instance_id: str = os.environ.get("SERVER_INSTANCE", "")
        self._retry_cache = None
        self._scheduler: BackgroundScheduler | None = None
        self._job_stats: dict[str, JobStats] = {}
        self._job_start_times: dict[str, float] = {}
        self._lock = threading.RLock()
        self._running = False
        self._job_registry = JobRegistry(self)
        self._trigger_factory = TriggerFactory(self)
        self._cron_parser = CronParser(self)
        self._retry_manager = RetryManager(self)
        self._event_handler = EventHandler(self)
        self._stats_collector = StatsCollector(self)

    @property
    def scheduler(self) -> BackgroundScheduler | None:
        """获取调度器实例"""
        return self._scheduler

    @property
    def is_running(self) -> bool:
        """检查调度器是否正在运行"""
        return self._running and self._scheduler is not None

    def start_service(self, load_defaults: bool = False) -> bool:
        """启动调度器服务"""
        if self._scheduler and self._running:
            log.warn("调度器服务已经在运行中")
            return True

        try:
            self._scheduler = BackgroundScheduler(
                timezone=os.environ.get("TZ"),
                jobstores={
                    "default": MemoryJobStore(),
                    "brushtask": MemoryJobStore(),
                    "rsscheck": MemoryJobStore(),
                    "torrent_remove": MemoryJobStore(),
                    "download": MemoryJobStore(),
                    "plugin": MemoryJobStore(),
                },
                executors=self.DEFAULT_EXECUTORS.copy(),
                job_defaults=self.DEFAULT_JOB_DEFAULTS.copy(),
            )

            self._scheduler.add_listener(
                self._event_handler._job_event_listener,
                EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED | EVENT_JOB_SUBMITTED,
            )

            self._scheduler.start()
            self._running = True

            if load_defaults:
                from app.services.scheduler_jobs import load_default_jobs

                load_default_jobs(self)

            log.info("调度器服务已启动")
            return True

        except (ServiceError, RepositoryError):
            raise
        except Exception as e:
            log.error(f"启动调度器服务失败: {e}")
            ExceptionUtils.exception_traceback(e, "启动调度器服务失败")
            self._cleanup()
            return False

    def _cleanup(self) -> None:
        """清理资源"""
        self._scheduler = None
        self._running = False
        self._job_start_times.clear()

    def stop_service(self) -> bool:
        """停止调度器服务"""
        if not self._scheduler:
            log.warn("stop_service: 调度器未运行")
            return True

        try:
            self._scheduler.remove_all_jobs()
            self._scheduler.shutdown(wait=True)
            self._cleanup()
            with contextlib.suppress(Exception):
                remove_session()

            log.info("调度器服务已停止")
            return True

        except (ServiceError, RepositoryError):
            raise
        except Exception as e:
            log.error(f"停止调度器服务失败: {e}")
            ExceptionUtils.exception_traceback(e, "停止调度器服务失败")
            return False

    def start_job(self, task: dict[str, Any] | TaskConfig) -> Job | None:
        """启动单个定时任务"""
        return self._job_registry.start_job(task)

    def start_job_batch(self, tasks: list[dict[str, Any] | TaskConfig]) -> list[Job | None]:
        """批量启动定时任务"""
        return self._job_registry.start_job_batch(tasks)

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
        """注册 interval 类型定时任务（便捷方法）"""
        return self._trigger_factory.register_interval(
            job_id,
            func,
            seconds,
            minutes,
            hours,
            args,
            kwargs,
            jobstore,
            next_run_time,
            max_instances,
            misfire_grace_time,
            coalesce,
            name,
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
        """注册 date 类型一次性定时任务（便捷方法）"""
        return self._trigger_factory.register_date(
            job_id,
            func,
            run_date,
            args,
            kwargs,
            jobstore,
            max_instances,
            misfire_grace_time,
            coalesce,
            name,
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
        """注册 cron 类型定时任务（便捷方法）"""
        return self._trigger_factory.register_cron(
            job_id,
            func,
            cron,
            args,
            kwargs,
            jobstore,
            next_run_time,
            max_instances,
            misfire_grace_time,
            coalesce,
            name,
        )

    def register_smart_cron(
        self,
        job_id: str,
        func: Callable,
        cron: str,
        func_desc: str = "",
        args: tuple | None = None,
        kwargs: dict[str, Any] | None = None,
        jobstore: str = "default",
        next_run_time: Any | None = None,
        max_instances: int = 1,
        misfire_grace_time: int = 300,
        coalesce: bool = True,
        name: str | None = None,
    ) -> Job | None:
        """智能注册定时任务"""
        return self._cron_parser.register_smart_cron(
            job_id,
            func,
            cron,
            func_desc,
            args,
            kwargs,
            jobstore,
            next_run_time,
            max_instances,
            misfire_grace_time,
            coalesce,
            name,
        )

    def print_jobs(self, jobstore: str | None = None) -> None:
        """打印任务列表"""
        self._job_registry.print_jobs(jobstore)

    def remove_all_jobs(self, jobstore: str | None = None) -> bool:
        """移除所有任务"""
        return self._job_registry.remove_all_jobs(jobstore)

    def get_jobs(self, jobstore: str | None = None) -> list[Job]:
        """获取任务列表"""
        return self._job_registry.get_jobs(jobstore)

    def get_job(self, job_id: str, jobstore: str | None = None) -> Job | None:
        """获取单个任务"""
        return self._job_registry.get_job(job_id, jobstore)

    def remove_job(self, job_id: str, jobstore: str | None = None) -> bool:
        """移除单个任务"""
        return self._job_registry.remove_job(job_id, jobstore)

    def pause_job(self, job_id: str, jobstore: str | None = None) -> bool:
        """暂停任务"""
        return self._job_registry.pause_job(job_id, jobstore)

    def resume_job(self, job_id: str, jobstore: str | None = None) -> bool:
        """恢复任务"""
        return self._job_registry.resume_job(job_id, jobstore)

    def modify_job(self, job_id: str, jobstore: str | None = None, **changes: Any) -> bool:
        """修改任务配置"""
        return self._job_registry.modify_job(job_id, jobstore, **changes)

    def reschedule_job(
        self,
        job_id: str,
        jobstore: str | None = None,
        trigger=None,
        **trigger_args,
    ) -> Job | None:
        """重新调度任务"""
        return self._job_registry.reschedule_job(job_id, jobstore, trigger, **trigger_args)

    def get_job_statistics(self, job_id: str | None = None) -> dict[str, Any] | dict[str, dict[str, Any]]:
        """获取任务执行统计"""
        return self._stats_collector.get_job_statistics(job_id)

    def reset_job_statistics(self, job_id: str | None = None) -> bool:
        """重置任务执行统计"""
        return self._stats_collector.reset_job_statistics(job_id)

    def get_service_status(self) -> dict[str, Any]:
        """获取调度器服务状态"""
        return self._stats_collector.get_service_status()

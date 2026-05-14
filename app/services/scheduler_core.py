import datetime
import math
import os
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from apscheduler.events import (
    EVENT_JOB_ERROR,
    EVENT_JOB_EXECUTED,
    EVENT_JOB_MISSED,
    EVENT_JOB_SUBMITTED,
    JobExecutionEvent,
)
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.job import Job
from apscheduler.jobstores.base import JobLookupError
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import log
from app.db import remove_session
from app.utils import ExceptionUtils
from app.utils.commons import SingletonMeta


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
        # 更新平均执行时间
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
            'job_id': self.job_id,
            'total_runs': self.total_runs,
            'success_count': self.success_count,
            'failure_count': self.failure_count,
            'retry_count': self.retry_count,
            'last_run_time': self.last_run_time.isoformat() if self.last_run_time else None,
            'last_duration': self.last_duration,
            'avg_duration': round(self.avg_duration, 3),
            'last_error': self.last_error,
            'consecutive_failures': self.consecutive_failures
        }


@dataclass
class TaskConfig:
    """任务配置数据类"""
    job_id: str
    func: Callable
    name: str | None = None
    trigger: str = 'interval'
    args: tuple = field(default_factory=tuple)
    kwargs: dict[str, Any] = field(default_factory=dict)
    jobstore: str = 'default'
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
        if self.trigger not in ('interval', 'date', 'cron'):
            raise ValueError(f"不支持的 trigger 类型: {self.trigger}")
        if self.trigger == 'interval':
            if not any([self.hours, self.minutes, self.seconds]):
                raise ValueError("interval 类型任务需要设置 hours/minutes/seconds 至少一个")
        if self.trigger == 'date' and not self.run_date:
            raise ValueError("date 类型任务需要设置 run_date")
        if self.trigger == 'cron' and not self.cron:
            raise ValueError("cron 类型任务需要设置 cron 表达式")

    def to_scheduler_args(self) -> dict[str, Any]:
        """转换为 APScheduler 参数"""
        args = {
            'func': self.func,
            'args': self.args,
            'kwargs': self.kwargs,
            'id': self.job_id,
            'name': self.name,
            'jobstore': self.jobstore,
            'replace_existing': True,
            'max_instances': self.max_instances,
            'misfire_grace_time': self.misfire_grace_time,
            'coalesce': self.coalesce
        }

        if self.trigger == 'interval':
            trigger_args = {}
            if self.hours is not None:
                trigger_args['hours'] = self.hours
            if self.minutes is not None:
                trigger_args['minutes'] = self.minutes
            if self.seconds is not None:
                trigger_args['seconds'] = self.seconds
            args['trigger'] = 'interval'
            args.update(trigger_args)
        elif self.trigger == 'date':
            args['trigger'] = 'date'
            args['run_date'] = self.run_date
        elif self.trigger == 'cron':
            args['trigger'] = CronTrigger.from_crontab(self.cron)
        else:
            args['trigger'] = self.trigger

        if self.next_run_time is not None:
            args['next_run_time'] = self.next_run_time

        return args


class SchedulerCore(metaclass=SingletonMeta):
    """调度器核心服务

    提供任务调度、执行监控、失败重试、统计收集等功能。
    使用单例模式确保全局只有一个调度器实例。
    """

    # 默认 jobstore 配置
    DEFAULT_JOBSTORES = {
        'default': MemoryJobStore(),
        'brushtask': MemoryJobStore(),
        'rsscheck': MemoryJobStore(),
        'torrent_remove': MemoryJobStore(),
        'download': MemoryJobStore(),
        'plugin': MemoryJobStore()
    }

    # 默认执行器配置
    DEFAULT_EXECUTORS = {
        'default': ThreadPoolExecutor(50)
    }

    # 默认任务默认配置
    DEFAULT_JOB_DEFAULTS = {
        'coalesce': True,
        'max_instances': 100,
        'misfire_grace_time': 300
    }

    # 最大重试次数
    MAX_RETRY_COUNT = 3

    # 重试延迟（秒）
    RETRY_DELAY = 60

    def __init__(self):
        self._instance_id: str = os.environ.get('SERVER_INSTANCE', '')
        self._retry_cache = None
        self._scheduler: BackgroundScheduler | None = None
        self._job_stats: dict[str, JobStats] = {}
        self._job_start_times: dict[str, float] = {}
        self._lock = threading.RLock()
        self._running = False

    @property
    def SCHEDULER(self) -> BackgroundScheduler | None:
        """向后兼容：获取调度器实例"""
        return self._scheduler

    @SCHEDULER.setter
    def SCHEDULER(self, value: BackgroundScheduler | None) -> None:
        """向后兼容：设置调度器实例"""
        self._scheduler = value

    @property
    def INSTANCE(self) -> str:
        """向后兼容：获取实例 ID"""
        return self._instance_id

    @INSTANCE.setter
    def INSTANCE(self, value: str) -> None:
        """向后兼容：设置实例 ID"""
        self._instance_id = value

    @property
    def scheduler(self) -> BackgroundScheduler | None:
        """获取调度器实例"""
        return self._scheduler

    @property
    def is_running(self) -> bool:
        """检查调度器是否正在运行"""
        return self._running and self._scheduler is not None

    def _get_job_stats(self, job_id: str) -> JobStats:
        """获取或创建任务统计对象"""
        with self._lock:
            if job_id not in self._job_stats:
                self._job_stats[job_id] = JobStats(job_id=job_id)
            return self._job_stats[job_id]

    def start_job(self, task: dict[str, Any] | TaskConfig) -> Job | None:
        """启动单个定时任务

        Args:
            task: 任务配置，可以是字典或 TaskConfig 对象
                如果是字典，支持以下字段：
                - job_id: 任务唯一标识（必填）
                - func: 执行函数（必填）
                - trigger: 触发器类型，默认 'interval'
                - args: 位置参数，默认 ()
                - kwargs: 关键字参数，默认 {}
                - jobstore: 存储位置，默认 'default'
                - hours/minutes/seconds: 间隔时间参数
                - run_date: date 触发器的执行时间
                - next_run_time: 下次执行时间
                - max_instances: 最大并发实例数

        Returns:
            Job 对象或 None（如果添加失败）
        """
        if not task:
            log.warn("start_job: 任务配置为空")
            return None

        if not self._scheduler:
            log.error("start_job: 调度器未启动")
            return None

        try:
            # 转换为 TaskConfig
            if isinstance(task, dict):
                task_config = TaskConfig(
                    job_id=task.get('job_id', ''),
                    func=task.get('func'),
                    name=task.get('name'),
                    trigger=task.get('trigger', 'interval'),
                    args=tuple(task.get('args', [])),
                    kwargs=task.get('kwargs', {}),
                    jobstore=task.get('jobstore', 'default'),
                    hours=task.get('hours'),
                    minutes=task.get('minutes'),
                    seconds=task.get('seconds'),
                    cron=task.get('cron'),
                    run_date=task.get('run_date'),
                    next_run_time=task.get('next_run_time'),
                    max_instances=task.get('max_instances', 1),
                    misfire_grace_time=task.get('misfire_grace_time', 300),
                    coalesce=task.get('coalesce', True)
                )
            else:
                task_config = task

            # 验证配置
            task_config.validate()

            # 添加到调度器
            job = self._scheduler.add_job(**task_config.to_scheduler_args())

            # 初始化统计
            self._get_job_stats(task_config.job_id)

            log.info(f"任务已添加: {task_config.job_id} (jobstore={task_config.jobstore})")
            return job

        except Exception as e:
            log.error(f"添加任务失败: {e}")
            ExceptionUtils.exception_traceback(e)
            return None

    def start_job_batch(self, tasks: list[dict[str, Any] | TaskConfig]) -> list[Job | None]:
        """批量启动定时任务

        Args:
            tasks: 任务配置列表

        Returns:
            添加成功的 Job 对象列表
        """
        results = []
        for task in tasks:
            job = self.start_job(task)
            results.append(job)
        return results

    def register_interval(
        self,
        job_id: str,
        func: Callable,
        seconds: int | None = None,
        minutes: int | None = None,
        hours: int | None = None,
        args: tuple | None = None,
        kwargs: dict[str, Any] | None = None,
        jobstore: str = 'default',
        next_run_time: Any | None = None,
        max_instances: int = 1,
        misfire_grace_time: int = 300,
        coalesce: bool = True,
        name: str | None = None
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
        return self.start_job({
            'job_id': job_id,
            'func': func,
            'name': name,
            'trigger': 'interval',
            'args': args or (),
            'kwargs': kwargs or {},
            'jobstore': jobstore,
            'seconds': seconds,
            'minutes': minutes,
            'hours': hours,
            'next_run_time': next_run_time,
            'max_instances': max_instances,
            'misfire_grace_time': misfire_grace_time,
            'coalesce': coalesce
        })

    def register_date(
        self,
        job_id: str,
        func: Callable,
        run_date: datetime.datetime,
        args: tuple | None = None,
        kwargs: dict[str, Any] | None = None,
        jobstore: str = 'default',
        max_instances: int = 1,
        misfire_grace_time: int = 60,
        coalesce: bool = True,
        name: str | None = None
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
        return self.start_job({
            'job_id': job_id,
            'func': func,
            'name': name,
            'trigger': 'date',
            'args': args or (),
            'kwargs': kwargs or {},
            'jobstore': jobstore,
            'run_date': run_date,
            'max_instances': max_instances,
            'misfire_grace_time': misfire_grace_time,
            'coalesce': coalesce
        })

    def register_cron(
        self,
        job_id: str,
        func: Callable,
        cron: str,
        args: tuple | None = None,
        kwargs: dict[str, Any] | None = None,
        jobstore: str = 'default',
        next_run_time: Any | None = None,
        max_instances: int = 1,
        misfire_grace_time: int = 300,
        coalesce: bool = True,
        name: str | None = None
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
        return self.start_job({
            'job_id': job_id,
            'func': func,
            'name': name,
            'trigger': 'cron',
            'args': args or (),
            'kwargs': kwargs or {},
            'jobstore': jobstore,
            'cron': cron,
            'next_run_time': next_run_time,
            'max_instances': max_instances,
            'misfire_grace_time': misfire_grace_time,
            'coalesce': coalesce
        })

    def register_smart_cron(
        self,
        job_id: str,
        func: Callable,
        cron: str,
        func_desc: str = "",
        args: tuple | None = None,
        kwargs: dict[str, Any] | None = None,
        jobstore: str = 'default',
        next_run_time: Any | None = None,
        max_instances: int = 1,
        misfire_grace_time: int = 300,
        coalesce: bool = True,
        name: str | None = None
    ) -> Job | None:
        """
        智能注册定时任务，兼容多种 cron 写法：
          1、5位 cron 表达式
          2、时间范围，如08:00-09:00，表示在该时间范围内随机执行一次；
          3、固定时间，如08:00；
          4、间隔小时数，如23.5；
        """
        if not self._scheduler:
            log.error("register_smart_cron: 调度器未启动")
            return None

        if not next_run_time:
            from apscheduler.util import undefined
            next_run_time = undefined

        job = None
        cron = str(cron).strip() if cron else ""
        if not cron:
            return None

        if cron.count(" ") == 4:
            try:
                job = self._scheduler.add_job(
                    func=func,
                    args=args or (),
                    kwargs=kwargs or {},
                    id=job_id,
                    name=name,
                    trigger=CronTrigger.from_crontab(cron),
                    next_run_time=next_run_time,
                    replace_existing=True,
                    jobstore=jobstore,
                    max_instances=max_instances,
                    misfire_grace_time=misfire_grace_time,
                    coalesce=coalesce
                )
            except Exception as e:
                log.info("%s时间cron表达式配置格式错误：%s %s" % (func_desc, cron, str(e)))
        elif '-' in cron:
            try:
                time_range = cron.split("-")
                start_time_range_str = time_range[0]
                end_time_range_str = time_range[1]
                start_time_range_array = start_time_range_str.split(":")
                end_time_range_array = end_time_range_str.split(":")
                start_hour = int(start_time_range_array[0])
                start_minute = int(start_time_range_array[1])
                end_hour = int(end_time_range_array[0])
                end_minute = int(end_time_range_array[1])

                def start_random_job():
                    task_time_count = random.randint(
                        start_hour * 60 + start_minute, end_hour * 60 + end_minute)
                    self._register_range_job(
                        func=func,
                        func_desc=func_desc,
                        job_id=f"{job_id}_1",
                        hour=math.floor(task_time_count / 60),
                        minute=task_time_count % 60,
                        args=args,
                        kwargs=kwargs,
                        jobstore=jobstore,
                        next_run_time=next_run_time,
                        max_instances=max_instances,
                        misfire_grace_time=misfire_grace_time,
                        coalesce=coalesce
                    )

                job = self._scheduler.add_job(
                    start_random_job,
                    "cron",
                    id=job_id,
                    name=name,
                    hour=start_hour,
                    minute=start_minute,
                    next_run_time=next_run_time,
                    replace_existing=True,
                    jobstore=jobstore,
                    max_instances=max_instances,
                    misfire_grace_time=misfire_grace_time,
                    coalesce=coalesce
                )
                log.info("%s服务时间范围随机模式启动，起始时间于%s:%s" % (
                    func_desc, str(start_hour).rjust(2, '0'), str(start_minute).rjust(2, '0')))
            except Exception as e:
                log.info("%s时间 时间范围随机模式 配置格式错误：%s %s" % (func_desc, cron, str(e)))
        elif ':' in cron:
            try:
                hour = int(cron.split(":")[0])
                minute = int(cron.split(":")[1])
            except Exception as e:
                log.info("%s时间 配置格式错误：%s" % (func_desc, str(e)))
                hour = minute = 0
            job = self._scheduler.add_job(
                func,
                "cron",
                args=args or (),
                kwargs=kwargs or {},
                id=job_id,
                name=name,
                hour=hour,
                minute=minute,
                next_run_time=next_run_time,
                replace_existing=True,
                jobstore=jobstore,
                max_instances=max_instances,
                misfire_grace_time=misfire_grace_time,
                coalesce=coalesce
            )
            log.info("%s服务启动" % func_desc)
        else:
            try:
                hours = float(cron)
            except Exception as e:
                log.info("%s时间 配置格式错误：%s" % (func_desc, str(e)))
                hours = 0
            if hours:
                job = self._scheduler.add_job(
                    func,
                    "interval",
                    args=args or (),
                    kwargs=kwargs or {},
                    id=job_id,
                    name=name,
                    hours=hours,
                    next_run_time=next_run_time,
                    replace_existing=True,
                    jobstore=jobstore,
                    max_instances=max_instances,
                    misfire_grace_time=misfire_grace_time,
                    coalesce=coalesce
                )
                log.info("%s服务启动" % func_desc)
        return job

    def _register_range_job(self, func, func_desc, hour, minute, job_id=None, args=None, kwargs=None,
                            jobstore='default', next_run_time=None, max_instances=1,
                            misfire_grace_time=300, coalesce=True):
        year = datetime.datetime.now().year
        month = datetime.datetime.now().month
        day = datetime.datetime.now().day
        second = random.randint(1, 59)
        log.info("%s到时间 即将在%s-%s-%s,%s:%s:%s执行" % (
            func_desc, str(year), str(month), str(day), str(hour), str(minute), str(second)))
        if hour < 0 or hour > 24:
            hour = -1
        if minute < 0 or minute > 60:
            minute = -1
        if hour < 0 or minute < 0:
            log.warn("%s时间 配置格式错误：不启动任务" % func_desc)
            return
        self._scheduler.add_job(
            func,
            "date",
            id=job_id,
            args=args or (),
            kwargs=kwargs or {},
            run_date=datetime.datetime(year, month, day, hour, minute, second),
            next_run_time=next_run_time,
            replace_existing=True,
            jobstore=jobstore,
            max_instances=max_instances,
            misfire_grace_time=misfire_grace_time,
            coalesce=coalesce
        )

    def print_jobs(self, jobstore: str | None = None) -> None:
        """打印任务列表

        Args:
            jobstore: 指定 jobstore，None 表示全部
        """
        if not self._scheduler:
            log.warn("print_jobs: 调度器未启动")
            return

        try:
            if jobstore:
                self._scheduler.print_jobs(jobstore=jobstore)
            else:
                self._scheduler.print_jobs()
        except Exception as e:
            log.error(f"打印任务列表失败: {e}")

    def remove_all_jobs(self, jobstore: str | None = None) -> bool:
        """移除所有任务

        Args:
            jobstore: 指定 jobstore，None 表示全部

        Returns:
            是否成功
        """
        if not self._scheduler:
            log.warn("remove_all_jobs: 调度器未启动")
            return False

        try:
            if jobstore:
                self._scheduler.remove_all_jobs(jobstore=jobstore)
                log.info(f"已移除 jobstore '{jobstore}' 的所有任务")
            else:
                self._scheduler.remove_all_jobs()
                log.info("已移除所有任务")
            return True
        except Exception as e:
            log.error(f"移除任务失败: {e}")
            return False

    def get_jobs(self, jobstore: str | None = None) -> list[Job]:
        """获取任务列表

        Args:
            jobstore: 指定 jobstore，None 表示全部

        Returns:
            Job 对象列表
        """
        if not self._scheduler:
            return []

        try:
            if jobstore:
                return self._scheduler.get_jobs(jobstore=jobstore)
            else:
                return self._scheduler.get_jobs()
        except Exception as e:
            log.error(f"获取任务列表失败: {e}")
            return []

    def get_job(self, job_id: str, jobstore: str | None = None) -> Job | None:
        """获取单个任务

        Args:
            job_id: 任务 ID
            jobstore: 指定 jobstore

        Returns:
            Job 对象或 None
        """
        if not self._scheduler:
            return None

        try:
            return self._scheduler.get_job(job_id=job_id, jobstore=jobstore)
        except Exception as e:
            log.error(f"获取任务 {job_id} 失败: {e}")
            return None

    def remove_job(self, job_id: str, jobstore: str | None = None) -> bool:
        """移除单个任务

        Args:
            job_id: 任务 ID
            jobstore: 指定 jobstore

        Returns:
            是否成功
        """
        if not self._scheduler:
            log.warn(f"remove_job: 调度器未启动，无法移除 {job_id}")
            return False

        try:
            self._scheduler.remove_job(job_id=job_id, jobstore=jobstore)
            log.info(f"任务已移除: {job_id}")
            # 清理统计
            with self._lock:
                if job_id in self._job_stats:
                    del self._job_stats[job_id]
            return True
        except JobLookupError:
            log.debug(f"任务 {job_id} 不存在，无需移除")
            return True
        except Exception as e:
            log.error(f"移除任务 {job_id} 失败: {e}")
            return False

    def pause_job(self, job_id: str, jobstore: str | None = None) -> bool:
        """暂停任务

        Args:
            job_id: 任务 ID
            jobstore: 指定 jobstore

        Returns:
            是否成功
        """
        job = self.get_job(job_id, jobstore)
        if not job:
            log.warn(f"pause_job: 任务 {job_id} 不存在")
            return False

        try:
            job.pause()
            log.info(f"任务已暂停: {job_id}")
            return True
        except Exception as e:
            log.error(f"暂停任务 {job_id} 失败: {e}")
            return False

    def resume_job(self, job_id: str, jobstore: str | None = None) -> bool:
        """恢复任务

        Args:
            job_id: 任务 ID
            jobstore: 指定 jobstore

        Returns:
            是否成功
        """
        job = self.get_job(job_id, jobstore)
        if not job:
            log.warn(f"resume_job: 任务 {job_id} 不存在")
            return False

        try:
            job.resume()
            # 清除重试计数
            self._clear_retry_count(job_id)
            log.info(f"任务已恢复: {job_id}")
            return True
        except Exception as e:
            log.error(f"恢复任务 {job_id} 失败: {e}")
            return False

    def modify_job(self, job_id: str, jobstore: str | None = None,
                   **changes: Any) -> bool:
        """修改任务配置

        Args:
            job_id: 任务 ID
            jobstore: 指定 jobstore
            **changes: 要修改的参数

        Returns:
            是否成功
        """
        job = self.get_job(job_id, jobstore)
        if not job:
            log.warn(f"modify_job: 任务 {job_id} 不存在")
            return False

        try:
            job.modify(**changes)
            log.info(f"任务已修改: {job_id}, 变更: {changes}")
            return True
        except Exception as e:
            log.error(f"修改任务 {job_id} 失败: {e}")
            return False

    def reschedule_job(self, job_id: str, jobstore: str | None = None, trigger=None, **trigger_args) -> Job | None:
        """重新调度任务

        Args:
            job_id: 任务 ID
            jobstore: 指定 jobstore
            trigger: 触发器类型或触发器对象
            **trigger_args: 触发器参数

        Returns:
            Job 对象或 None
        """
        if not self._scheduler:
            log.warn(f"reschedule_job: 调度器未启动，无法重新调度 {job_id}")
            return None

        try:
            return self._scheduler.reschedule_job(job_id, jobstore=jobstore, trigger=trigger, **trigger_args)
        except Exception as e:
            log.error(f"重新调度任务 {job_id} 失败: {e}")
            return None

    def start_service(self, load_defaults: bool = False) -> bool:
        """启动调度器服务

        Args:
            load_defaults: 启动后是否加载系统默认任务

        Returns:
            是否成功启动
        """
        if self._scheduler and self._running:
            log.warn("调度器服务已经在运行中")
            return True

        try:

            # 创建调度器（每次启动都使用新的 jobstore 实例，避免任务残留）
            self._scheduler = BackgroundScheduler(
                timezone=os.environ.get('TZ'),
                jobstores={
                    'default': MemoryJobStore(),
                    'brushtask': MemoryJobStore(),
                    'rsscheck': MemoryJobStore(),
                    'torrent_remove': MemoryJobStore(),
                    'download': MemoryJobStore(),
                    'plugin': MemoryJobStore()
                },
                executors=self.DEFAULT_EXECUTORS.copy(),
                job_defaults=self.DEFAULT_JOB_DEFAULTS.copy()
            )

            # 添加事件监听器
            self._scheduler.add_listener(
                self._job_event_listener,
                EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED | EVENT_JOB_SUBMITTED
            )

            # 启动调度器
            self._scheduler.start()
            self._running = True

            if load_defaults:
                from app.services.scheduler_jobs import load_default_jobs
                load_default_jobs(self)

            log.info("调度器服务已启动")
            return True

        except Exception as e:
            log.error(f"启动调度器服务失败: {e}")
            ExceptionUtils.exception_traceback(e)
            self._cleanup()
            return False

    def _cleanup(self) -> None:
        """清理资源"""
        self._scheduler = None
        self._running = False
        self._job_start_times.clear()

    def stop_service(self) -> bool:
        """停止调度器服务

        Returns:
            是否成功停止
        """
        if not self._scheduler:
            log.warn("stop_service: 调度器未运行")
            return True

        try:
            # 停止所有任务
            self._scheduler.remove_all_jobs()

            # 关闭调度器
            self._scheduler.shutdown(wait=True)

            # 清理资源
            self._cleanup()

            # 清理数据库 session
            try:
                remove_session()
            except Exception:
                pass

            log.info("调度器服务已停止")
            return True

        except Exception as e:
            log.error(f"停止调度器服务失败: {e}")
            ExceptionUtils.exception_traceback(e)
            return False

    def _job_event_listener(self, event: JobExecutionEvent) -> None:
        """任务事件监听器

        处理任务执行完成、失败、错过等事件，
        同时清理数据库 session 防止连接池泄漏。

        Args:
            event: APScheduler 事件对象
        """
        job_id = event.job_id

        # 清理当前线程的数据库 session
        try:
            remove_session()
        except Exception:
            pass

        if event.code == EVENT_JOB_SUBMITTED:
            self._job_start_times[job_id] = time.time()
        elif event.code == EVENT_JOB_EXECUTED:
            self._handle_job_success(job_id, event)
        elif event.code == EVENT_JOB_ERROR:
            self._handle_job_failure(job_id, event)
        elif event.code == EVENT_JOB_MISSED:
            self._handle_job_missed(job_id, event)

    def _handle_job_success(self, job_id: str, event: JobExecutionEvent) -> None:
        """处理任务成功执行"""
        # 计算执行时间
        start_time = self._job_start_times.pop(job_id, None)
        duration = time.time() - start_time if start_time else 0

        # 更新统计
        stats = self._get_job_stats(job_id)
        stats.record_success(duration)

        # 清除重试计数
        self._clear_retry_count(job_id)

        log.info(f"任务执行成功: {job_id}, 耗时: {duration:.3f}s")

    def _handle_job_failure(self, job_id: str, event: JobExecutionEvent) -> None:
        """处理任务执行失败"""
        exception = event.exception if hasattr(event, 'exception') else 'Unknown error'
        traceback = event.traceback if hasattr(event, 'traceback') else ''

        # 更新统计
        stats = self._get_job_stats(job_id)
        stats.record_failure(str(exception))

        log.error(f"任务执行失败: {job_id}, 异常: {exception}")
        if traceback:
            log.debug(f"任务 {job_id} 异常堆栈:\n{traceback}")

        # 尝试重试
        self._retry_failed_job(job_id)

    def _handle_job_missed(self, job_id: str, event: JobExecutionEvent) -> None:
        """处理任务错过执行"""
        log.warn(f"任务错过执行: {job_id}")

    def _get_retry_cache(self):
        """获取重试计数缓存（内存/Redis自动降级）"""
        if self._retry_cache is None:
            from app.infrastructure.cache_system import get_cache_manager
            self._retry_cache = get_cache_manager().get_or_create(
                "scheduler_retry", cache_type="tiered", maxsize=1000
            )
        return self._retry_cache

    def _get_retry_key(self, job_id: str) -> str:
        """获取重试计数的缓存 key"""
        return f"scheduler:retry:{self._instance_id}:{job_id}"

    def _get_retry_count(self, job_id: str) -> int:
        """获取任务重试次数"""
        try:
            cache = self._get_retry_cache()
            retry_key = self._get_retry_key(job_id)
            count = cache.get(retry_key)
            return int(count) if count is not None else 0
        except Exception as e:
            log.error(f"获取重试次数失败 {job_id}: {e}")
            return 0

    def _set_retry_count(self, job_id: str, count: int) -> bool:
        """设置任务重试次数"""
        try:
            cache = self._get_retry_cache()
            retry_key = self._get_retry_key(job_id)
            cache.set(retry_key, count, ttl=3600)  # 1小时过期
            return True
        except Exception as e:
            log.error(f"设置重试次数失败 {job_id}: {e}")
            return False

    def _clear_retry_count(self, job_id: str) -> bool:
        """清除任务重试次数"""
        try:
            cache = self._get_retry_cache()
            retry_key = self._get_retry_key(job_id)
            cache.delete(retry_key)
            return True
        except Exception as e:
            log.error(f"清除重试次数失败 {job_id}: {e}")
            return False

    def _retry_failed_job(self, job_id: str) -> bool:
        """重试失败的任务

        使用延迟调度方式重新执行失败的任务，
        最多重试 MAX_RETRY_COUNT 次。

        Args:
            job_id: 任务 ID

        Returns:
            是否成功安排重试
        """
        job = self.get_job(job_id)
        if not job:
            log.warn(f"_retry_failed_job: 任务 {job_id} 不存在，无法重试")
            return False

        # 检查重试次数
        retry_count = self._get_retry_count(job_id)

        if retry_count >= self.MAX_RETRY_COUNT:
            log.error(f"任务 {job_id} 已达到最大重试次数 {self.MAX_RETRY_COUNT}")
            self._clear_retry_count(job_id)
            return False

        # 增加重试计数
        self._set_retry_count(job_id, retry_count + 1)

        # 更新统计
        stats = self._get_job_stats(job_id)
        stats.record_retry()

        # 计算重试延迟（指数退避）
        delay = self.RETRY_DELAY * (2 ** retry_count)
        next_run_time = datetime.datetime.now() + datetime.timedelta(seconds=delay)

        try:
            # 使用 add_job 创建一次性重试任务
            retry_job_id = f"{job_id}_retry_{retry_count + 1}"
            jobstore = getattr(job, '_jobstore_alias', 'default')
            self._scheduler.add_job(
                func=job.func,
                args=job.args,
                kwargs=job.kwargs,
                trigger='date',
                run_date=next_run_time,
                id=retry_job_id,
                jobstore=jobstore,
                replace_existing=True,
                misfire_grace_time=60
            )

            log.info(f"任务 {job_id} 已安排重试 #{retry_count + 1}, "
                    f"将在 {delay} 秒后执行 ({next_run_time.strftime('%Y-%m-%d %H:%M:%S')})")
            return True

        except Exception as e:
            log.error(f"安排任务 {job_id} 重试失败: {e}")
            return False

    def get_job_statistics(self, job_id: str | None = None) -> dict[str, Any] | dict[str, dict[str, Any]]:
        """获取任务执行统计

        Args:
            job_id: 指定任务 ID，None 返回所有统计

        Returns:
            任务统计字典
        """
        with self._lock:
            if job_id:
                stats = self._job_stats.get(job_id)
                return stats.to_dict() if stats else {}
            else:
                return {jid: stats.to_dict() for jid, stats in self._job_stats.items()}

    def reset_job_statistics(self, job_id: str | None = None) -> bool:
        """重置任务执行统计

        Args:
            job_id: 指定任务 ID，None 重置所有

        Returns:
            是否成功
        """
        with self._lock:
            if job_id:
                if job_id in self._job_stats:
                    self._job_stats[job_id] = JobStats(job_id=job_id)
                    log.info(f"任务 {job_id} 统计已重置")
                    return True
                return False
            else:
                self._job_stats.clear()
                log.info("所有任务统计已重置")
                return True

    def get_service_status(self) -> dict[str, Any]:
        """获取调度器服务状态

        Returns:
            服务状态字典
        """
        status = {
            'running': self._running,
            'instance_id': self._instance_id,
            'job_count': 0,
            'jobstores': list(self.DEFAULT_JOBSTORES.keys()),
            'statistics': self.get_job_statistics()
        }

        if self._scheduler:
            try:
                status['job_count'] = len(self._scheduler.get_jobs())
            except Exception:
                pass

        return status

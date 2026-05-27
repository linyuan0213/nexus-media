"""任务注册与管理组件."""

from collections.abc import Callable
from typing import Any

from apscheduler.job import Job
from apscheduler.jobstores.base import JobLookupError

import log
from app.core.exceptions import RepositoryError, ServiceError
from app.infrastructure.distributed_lock.lock_manager import get_lock_manager
from app.services.scheduler.models import TaskConfig
from app.utils import ExceptionUtils


class JobRegistry:
    """任务注册与管理组件"""

    def __init__(self, core):
        self._core = core

    @staticmethod
    def _wrap_with_lock(func, job_id: str, lock_ttl: int = 300):
        """包装任务函数，执行前获取分布式锁."""
        if func is None:
            return func

        def wrapped(*args, **kwargs):
            lock_key = f"scheduler:lock:{job_id}"
            lock = get_lock_manager().create_lock(lock_key, lock_ttl)
            acquired = lock.acquire()
            if not acquired:
                log.info(f"【Scheduler】任务 {job_id} 跳过执行（锁被占用）")
                return None
            try:
                return func(*args, **kwargs)
            finally:
                lock.release()

        return wrapped

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

        if not self._core._scheduler:
            log.error("start_job: 调度器未启动")
            return None

        try:
            # 转换为 TaskConfig
            if isinstance(task, dict):
                task_config = TaskConfig(
                    job_id=task.get("job_id", ""),
                    func=task.get("func") or (lambda: None),
                    name=task.get("name"),
                    trigger=task.get("trigger", "interval"),
                    args=tuple(task.get("args", [])),
                    kwargs=task.get("kwargs", {}),
                    jobstore=task.get("jobstore", "default"),
                    hours=task.get("hours"),
                    minutes=task.get("minutes"),
                    seconds=task.get("seconds"),
                    cron=task.get("cron"),
                    run_date=task.get("run_date"),
                    next_run_time=task.get("next_run_time"),
                    max_instances=task.get("max_instances", 1),
                    misfire_grace_time=task.get("misfire_grace_time", 300),
                    coalesce=task.get("coalesce", True),
                )
            else:
                task_config = task

            # 验证配置
            task_config.validate()

            # 包装函数添加分布式锁
            from typing import cast

            original_func = task_config.func
            task_config.func = cast(Callable, self._wrap_with_lock(original_func, task_config.job_id))

            # 添加到调度器
            job = self._core._scheduler.add_job(**task_config.to_scheduler_args())

            # 初始化统计
            self._core._stats_collector._get_job_stats(task_config.job_id)

            log.info(f"任务已添加: {task_config.job_id} (jobstore={task_config.jobstore})")
            return job

        except (ServiceError, RepositoryError):
            raise
        except Exception as e:
            log.error(f"添加任务失败: {e}")
            ExceptionUtils.exception_traceback(e, "调度器添加任务失败")
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

    def print_jobs(self, jobstore: str | None = None) -> None:
        """打印任务列表

        Args:
            jobstore: 指定 jobstore，None 表示全部
        """
        if not self._core._scheduler:
            log.warn("print_jobs: 调度器未启动")
            return

        try:
            if jobstore:
                self._core._scheduler.print_jobs(jobstore=jobstore)
            else:
                self._core._scheduler.print_jobs()
        except (ServiceError, RepositoryError):
            raise
        except Exception as e:
            log.error(f"打印任务列表失败: {e}")

    def remove_all_jobs(self, jobstore: str | None = None) -> bool:
        """移除所有任务

        Args:
            jobstore: 指定 jobstore，None 表示全部

        Returns:
            是否成功
        """
        if not self._core._scheduler:
            log.warn("remove_all_jobs: 调度器未启动")
            return False

        try:
            if jobstore:
                self._core._scheduler.remove_all_jobs(jobstore=jobstore)
                log.info(f"已移除 jobstore '{jobstore}' 的所有任务")
            else:
                self._core._scheduler.remove_all_jobs()
                log.info("已移除所有任务")
            return True
        except (ServiceError, RepositoryError):
            raise
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
        if not self._core._scheduler:
            return []

        try:
            if jobstore:
                return self._core._scheduler.get_jobs(jobstore=jobstore)
            else:
                return self._core._scheduler.get_jobs()
        except (ServiceError, RepositoryError):
            raise
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
        if not self._core._scheduler:
            return None

        try:
            return self._core._scheduler.get_job(job_id=job_id, jobstore=jobstore)
        except (ServiceError, RepositoryError):
            raise
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
        if not self._core._scheduler:
            log.warn(f"remove_job: 调度器未启动，无法移除 {job_id}")
            return False

        try:
            self._core._scheduler.remove_job(job_id=job_id, jobstore=jobstore)
            log.info(f"任务已移除: {job_id}")
            # 清理统计
            with self._core._lock:
                if job_id in self._core._job_stats:
                    del self._core._job_stats[job_id]
            return True
        except JobLookupError:
            log.debug(f"任务 {job_id} 不存在，无需移除")
            return True
        except (ServiceError, RepositoryError):
            raise
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
        except (ServiceError, RepositoryError):
            raise
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
            self._core._retry_manager._clear_retry_count(job_id)
            log.info(f"任务已恢复: {job_id}")
            return True
        except (ServiceError, RepositoryError):
            raise
        except Exception as e:
            log.error(f"恢复任务 {job_id} 失败: {e}")
            return False

    def modify_job(self, job_id: str, jobstore: str | None = None, **changes: Any) -> bool:
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
        except (ServiceError, RepositoryError):
            raise
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
        if not self._core._scheduler:
            log.warn(f"reschedule_job: 调度器未启动，无法重新调度 {job_id}")
            return None

        try:
            return self._core._scheduler.reschedule_job(job_id, jobstore=jobstore, trigger=trigger, **trigger_args)
        except (ServiceError, RepositoryError):
            raise
        except Exception as e:
            log.error(f"重新调度任务 {job_id} 失败: {e}")
            return None

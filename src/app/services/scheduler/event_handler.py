"""事件监听与处理组件."""

import time

from apscheduler.events import (
    EVENT_JOB_ERROR,
    EVENT_JOB_EXECUTED,
    EVENT_JOB_MISSED,
    EVENT_JOB_SUBMITTED,
    JobExecutionEvent,
)

import log


class EventHandler:
    """事件监听与处理组件"""

    def __init__(self, core):
        self._core = core

    def _job_event_listener(self, event: JobExecutionEvent) -> None:
        """任务事件监听器

        处理任务执行完成、失败、错过等事件。
        数据库 session 清理由 JobRegistry._wrap_with_lock 在作业线程中完成。

        Args:
            event: APScheduler 事件对象
        """
        job_id = event.job_id

        if event.code == EVENT_JOB_SUBMITTED:
            self._core._job_start_times[job_id] = time.time()
        elif event.code == EVENT_JOB_EXECUTED:
            self._handle_job_success(job_id, event)
        elif event.code == EVENT_JOB_ERROR:
            self._handle_job_failure(job_id, event)
        elif event.code == EVENT_JOB_MISSED:
            self._handle_job_missed(job_id, event)

    def _handle_job_success(self, job_id: str, event: JobExecutionEvent) -> None:
        """处理任务成功执行"""
        # 计算执行时间
        start_time = self._core._job_start_times.pop(job_id, None)
        duration = time.time() - start_time if start_time else 0

        # 更新统计
        stats = self._core._stats_collector._get_job_stats(job_id)
        stats.record_success(duration)

        # 清除重试计数
        self._core._retry_manager._clear_retry_count(job_id)

        log.info(f"任务执行成功: {job_id}, 耗时: {duration:.3f}s")

    def _handle_job_failure(self, job_id: str, event: JobExecutionEvent) -> None:
        """处理任务执行失败"""
        exception = event.exception if hasattr(event, "exception") else "Unknown error"
        traceback = event.traceback if hasattr(event, "traceback") else ""

        # 更新统计
        stats = self._core._stats_collector._get_job_stats(job_id)
        stats.record_failure(str(exception))

        log.error(f"任务执行失败: {job_id}, 异常: {exception}")
        if traceback:
            log.debug(f"任务 {job_id} 异常堆栈:\n{traceback}")

        # 尝试重试
        self._core._retry_manager._retry_failed_job(job_id)

    def _handle_job_missed(self, job_id: str, event: JobExecutionEvent) -> None:
        """处理任务错过执行"""
        log.warn(f"任务错过执行: {job_id}")

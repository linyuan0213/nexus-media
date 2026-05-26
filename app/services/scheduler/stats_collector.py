"""任务统计组件."""

import contextlib
from typing import Any

import log
from app.services.scheduler.models import JobStats


class StatsCollector:
    """任务统计组件"""

    def __init__(self, core):
        self._core = core

    def _get_job_stats(self, job_id: str) -> JobStats:
        """获取或创建任务统计对象"""
        with self._core._lock:
            if job_id not in self._core._job_stats:
                self._core._job_stats[job_id] = JobStats(job_id=job_id)
            return self._core._job_stats[job_id]

    def get_job_statistics(self, job_id: str | None = None) -> dict[str, Any] | dict[str, dict[str, Any]]:
        """获取任务执行统计

        Args:
            job_id: 指定任务 ID，None 返回所有统计

        Returns:
            任务统计字典
        """
        with self._core._lock:
            if job_id:
                stats = self._core._job_stats.get(job_id)
                return stats.to_dict() if stats else {}
            else:
                return {jid: stats.to_dict() for jid, stats in self._core._job_stats.items()}

    def reset_job_statistics(self, job_id: str | None = None) -> bool:
        """重置任务执行统计

        Args:
            job_id: 指定任务 ID，None 重置所有

        Returns:
            是否成功
        """
        with self._core._lock:
            if job_id:
                if job_id in self._core._job_stats:
                    self._core._job_stats[job_id] = JobStats(job_id=job_id)
                    log.info(f"任务 {job_id} 统计已重置")
                    return True
                return False
            else:
                self._core._job_stats.clear()
                log.info("所有任务统计已重置")
                return True

    def get_service_status(self) -> dict[str, Any]:
        """获取调度器服务状态

        Returns:
            服务状态字典
        """
        status = {
            "running": self._core._running,
            "instance_id": self._core._instance_id,
            "job_count": 0,
            "jobstores": list(self._core.DEFAULT_JOBSTORES.keys()),
            "statistics": self._core.get_job_statistics(),
        }

        if self._core._scheduler:
            with contextlib.suppress(Exception):
                status["job_count"] = len(self._core._scheduler.get_jobs())

        return status

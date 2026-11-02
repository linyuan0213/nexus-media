"""通用任务队列抽象接口."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.infrastructure.task_queue.models import Task


class TaskQueue(ABC):
    """持久任务队列接口。

    Redis 后端 durable=True；内存后端 durable=False，仅保证进程存活期间。
    handler 应保持短执行时间；长时间下载由业务层监控，不占用队列租约。
    """

    def __init__(
        self,
        queue_name: str,
        *,
        lease_seconds: int = 120,
        max_attempts: int = 5,
        dedup_ttl_seconds: int = 86400,
        priority: int = 0,
    ):
        self.queue_name = queue_name
        self.lease_seconds = max(1, int(lease_seconds))
        self.max_attempts = max(1, int(max_attempts))
        self.dedup_ttl_seconds = max(0, int(dedup_ttl_seconds))
        self.priority = int(priority)

    @property
    @abstractmethod
    def durable(self) -> bool:
        """是否具备跨进程/重启持久性."""

    @abstractmethod
    def enqueue(
        self,
        task_type: str,
        payload: dict[str, Any],
        *,
        dedup_key: str = "",
        priority: int | None = None,
        max_attempts: int | None = None,
        task_id: str | None = None,
    ) -> Task:
        """入队；dedup_key 已存在时返回已有任务，不重复写入."""

    @abstractmethod
    def claim(self, consumer: str, *, count: int = 1, block_ms: int = 1000) -> list[Task]:
        """领取任务并写入租约；无任务时最多阻塞 block_ms."""

    @abstractmethod
    def heartbeat(self, task: Task) -> bool:
        """续租；handler 执行时间可能超过 lease 时调用."""

    @abstractmethod
    def ack(self, task: Task, result: dict[str, Any] | None = None) -> bool:
        """确认成功."""

    @abstractmethod
    def fail(self, task: Task, error: str, *, retryable: bool = True) -> bool:
        """记录失败；可重试任务回到队列，否则进入死信."""

    @abstractmethod
    def cancel(self, task: Task) -> bool:
        """取消任务."""

    @abstractmethod
    def get(self, task_id: str) -> Task | None:
        """按 ID 查询任务状态."""

    @abstractmethod
    def pending(self) -> int:
        """待处理（含未确认）任务数."""

    def close(self) -> None:
        """释放资源，默认无操作."""

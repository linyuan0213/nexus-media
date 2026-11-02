"""进程内任务队列 — Redis 未启用时的 best-effort 后端."""

from __future__ import annotations

import heapq
import threading
import time
from typing import Any

from app.infrastructure.task_queue.base import TaskQueue
from app.infrastructure.task_queue.models import Task, TaskQueueError, TaskStatus


class MemoryTaskQueue(TaskQueue):
    """内存队列：仅保证进程存活期间，重启后任务丢失."""

    def __init__(
        self,
        queue_name: str,
        *,
        maxsize: int = 1000,
        lease_seconds: int = 120,
        max_attempts: int = 5,
        dedup_ttl_seconds: int = 86400,
    ):
        super().__init__(
            queue_name,
            lease_seconds=lease_seconds,
            max_attempts=max_attempts,
            dedup_ttl_seconds=dedup_ttl_seconds,
        )
        self.maxsize = max(1, int(maxsize))
        self._lock = threading.Condition()
        self._ready: list[tuple[int, int, str]] = []
        self._sequence = 0
        self._tasks: dict[str, Task] = {}
        self._dedup: dict[str, tuple[str, float | None]] = {}
        self._closed = False

    @property
    def durable(self) -> bool:
        return False

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
        with self._lock:
            if self._closed:
                raise TaskQueueError("内存队列已关闭")
            if dedup_key:
                existing = self._find_dedup(dedup_key)
                if existing is not None:
                    return existing
            if len(self._ready) >= self.maxsize:
                raise TaskQueueError("内存队列已满")
            task = Task.create(
                self.queue_name,
                task_type,
                payload,
                dedup_key=dedup_key,
                priority=self.priority if priority is None else priority,
                max_attempts=self.max_attempts if max_attempts is None else max_attempts,
                task_id=task_id,
            )
            self._tasks[task.id] = task
            self._remember_dedup(task)
            self._push(task)
            self._lock.notify()
            return task

    def claim(self, consumer: str, *, count: int = 1, block_ms: int = 1000) -> list[Task]:
        deadline = time.monotonic() + max(0, block_ms) / 1000
        claimed: list[Task] = []
        with self._lock:
            while not self._ready and not self._closed:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._lock.wait(timeout=remaining)
            while self._ready and len(claimed) < max(1, count):
                _, _, task_id = heapq.heappop(self._ready)
                task = self._tasks.get(task_id)
                if task is None or task.status != TaskStatus.QUEUED:
                    continue
                now = time.time()
                task.status = TaskStatus.RUNNING
                task.lease_owner = consumer
                task.lease_until = now + self.lease_seconds
                task.updated_at = now
                claimed.append(task)
        return claimed

    def heartbeat(self, task: Task) -> bool:
        with self._lock:
            current = self._tasks.get(task.id)
            if current is None or current.status != TaskStatus.RUNNING:
                return False
            current.lease_until = time.time() + self.lease_seconds
            current.updated_at = time.time()
            return True

    def ack(self, task: Task, result: dict[str, Any] | None = None) -> bool:
        with self._lock:
            current = self._tasks.get(task.id)
            if current is None:
                return False
            current.status = TaskStatus.SUCCEEDED
            current.result = result
            current.lease_owner = ""
            current.lease_until = 0.0
            current.updated_at = time.time()
            return True

    def fail(self, task: Task, error: str, *, retryable: bool = True) -> bool:
        with self._lock:
            current = self._tasks.get(task.id)
            if current is None:
                return False
            current.attempts += 1
            current.last_error = error
            current.updated_at = time.time()
            if retryable and current.attempts < current.max_attempts:
                current.status = TaskStatus.QUEUED
                current.lease_owner = ""
                current.lease_until = 0.0
                self._push(current)
                self._lock.notify()
            elif retryable:
                current.status = TaskStatus.DEAD
            else:
                current.status = TaskStatus.FAILED
            return True

    def cancel(self, task: Task) -> bool:
        with self._lock:
            current = self._tasks.get(task.id)
            if current is None:
                return False
            current.status = TaskStatus.CANCELLED
            current.lease_owner = ""
            current.lease_until = 0.0
            current.updated_at = time.time()
            return True

    def get(self, task_id: str) -> Task | None:
        with self._lock:
            return self._tasks.get(task_id)

    def pending(self) -> int:
        with self._lock:
            running = sum(1 for task in self._tasks.values() if task.status == TaskStatus.RUNNING)
            return len(self._ready) + running

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._lock.notify_all()

    def _push(self, task: Task) -> None:
        self._sequence += 1
        heapq.heappush(self._ready, (-task.priority, self._sequence, task.id))

    def _remember_dedup(self, task: Task) -> None:
        if not task.dedup_key:
            return
        expires = time.time() + self.dedup_ttl_seconds if self.dedup_ttl_seconds else None
        self._dedup[task.dedup_key] = (task.id, expires)

    def _find_dedup(self, dedup_key: str) -> Task | None:
        item = self._dedup.get(dedup_key)
        if item is None:
            return None
        task_id, expires = item
        if expires is not None and expires <= time.time():
            self._dedup.pop(dedup_key, None)
            return None
        task = self._tasks.get(task_id)
        if task is None:
            self._dedup.pop(dedup_key, None)
            return None
        return task

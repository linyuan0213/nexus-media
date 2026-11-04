"""任务队列 worker：领取、执行、ACK/失败处理."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

import log
from app.db.engine import background_engine_context
from app.infrastructure.task_queue.base import TaskQueue
from app.infrastructure.task_queue.models import QueueUnavailableError, Task

TaskHandler = Callable[[Task], dict[str, Any] | None]


class TaskWorker:
    """按 queue 并发消费任务.

    handler 应短执行；长任务请拆成状态机或由业务监控器推进，避免占用租约。
    """

    def __init__(
        self,
        queue: TaskQueue,
        handlers: dict[str, TaskHandler],
        *,
        consumer: str = "",
        concurrency: int = 1,
        poll_block_ms: int = 1000,
        error_sleep_seconds: float = 1.0,
        heartbeat: bool = True,
    ):
        self._queue = queue
        self._handlers = handlers
        self._consumer = consumer or f"{queue.queue_name}-{uuid.uuid4().hex[:8]}"
        self._concurrency = max(1, int(concurrency))
        self._poll_block_ms = max(1, int(poll_block_ms))
        self._error_sleep_seconds = max(0.1, float(error_sleep_seconds))
        self._heartbeat_enabled = heartbeat
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        for index in range(self._concurrency):
            name = f"{self._consumer}-{index}"
            thread = threading.Thread(target=self._consume_loop, args=(name,), name=f"TaskWorker[{name}]", daemon=True)
            thread.start()
            self._threads.append(thread)
        log.info(
            f"[TaskQueue]worker 已启动 queue={self._queue.queue_name} "
            f"concurrency={self._concurrency} durable={self._queue.durable}"
        )

    def stop(self, timeout: float = 5.0) -> bool:
        self._stop.set()
        deadline = time.monotonic() + max(0.0, timeout)
        for thread in self._threads:
            thread.join(timeout=max(0.0, deadline - time.monotonic()))
        alive = [thread for thread in self._threads if thread.is_alive()]
        self._threads = alive
        if alive:
            log.warn(f"[TaskQueue]worker 仍有 {len(alive)} 个任务在运行，暂不关闭队列 queue={self._queue.queue_name}")
            return False
        self._started = False
        log.info(f"[TaskQueue]worker 已停止 queue={self._queue.queue_name}")
        return True

    def _consume_loop(self, consumer: str) -> None:
        while not self._stop.is_set():
            try:
                tasks = self._queue.claim(consumer, count=1, block_ms=self._poll_block_ms)
            except QueueUnavailableError as exc:
                log.warn(f"[TaskQueue]队列不可用，等待恢复: {exc}")
                self._wait()
                continue
            except Exception as exc:  # noqa: BLE001
                log.error(f"[TaskQueue]领取任务异常: {exc}")
                self._wait()
                continue
            for task in tasks:
                self._run_task(task)

    def _run_task(self, task: Task) -> None:
        handler = self._handlers.get(task.task_type)
        if handler is None:
            self._queue.fail(task, f"未注册任务类型: {task.task_type}", retryable=False)
            return
        heartbeat_stop = threading.Event()
        heartbeat_thread: threading.Thread | None = None
        if self._heartbeat_enabled:
            heartbeat_thread = threading.Thread(
                target=self._heartbeat_loop,
                args=(task, heartbeat_stop),
                name=f"TaskHeartbeat[{task.id[:8]}]",
                daemon=True,
            )
            heartbeat_thread.start()
        try:
            with background_engine_context():
                result = handler(task)
        except Exception as exc:  # noqa: BLE001
            log.warn(f"[TaskQueue]任务失败 {task.id} ({task.task_type}): {exc}")
            self._queue.fail(task, str(exc), retryable=True)
        else:
            self._queue.ack(task, result)
        finally:
            heartbeat_stop.set()
            if heartbeat_thread is not None:
                heartbeat_thread.join(timeout=1)

    def _heartbeat_loop(self, task: Task, stop: threading.Event) -> None:
        interval = max(1.0, min(self._queue.lease_seconds / 3, 10.0))
        while not stop.wait(interval):
            self._queue.heartbeat(task)

    def _wait(self) -> None:
        self._stop.wait(timeout=self._error_sleep_seconds)

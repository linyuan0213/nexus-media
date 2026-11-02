"""任务 worker 测试."""

import threading
import time

from app.infrastructure.task_queue.memory_queue import MemoryTaskQueue
from app.infrastructure.task_queue.models import TaskStatus
from app.infrastructure.task_queue.worker import TaskWorker


def test_worker_success():
    queue = MemoryTaskQueue("demo")
    done = threading.Event()
    received: list[str] = []

    def handler(task):
        received.append(task.task_type)
        done.set()
        return {"ok": True}

    worker = TaskWorker(queue, {"demo": handler}, concurrency=1, poll_block_ms=50)
    worker.start()
    try:
        task = queue.enqueue("demo", {})
        assert done.wait(2)
        _wait_until(lambda: _status(queue, task.id) is TaskStatus.SUCCEEDED)
        assert received == ["demo"]
    finally:
        worker.stop()


def test_worker_unknown_type_is_failed_without_retry():
    queue = MemoryTaskQueue("demo")
    worker = TaskWorker(queue, {}, concurrency=1, poll_block_ms=50)
    worker.start()
    try:
        task = queue.enqueue("unknown", {})
        _wait_until(lambda: _status(queue, task.id) is TaskStatus.FAILED)
    finally:
        worker.stop()


def _wait_until(predicate, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition not met in time")


def _status(queue, task_id: str):
    task = queue.get(task_id)
    return task.status if task is not None else None

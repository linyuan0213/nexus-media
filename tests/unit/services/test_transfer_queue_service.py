"""转移任务队列测试."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock

from app.infrastructure.task_queue import Task, TaskStatus
from app.infrastructure.task_queue.memory_queue import MemoryTaskQueue
from app.services import transfer_queue_service as module
from app.services.transfer_queue_service import TransferQueueService


class _FakeClient:
    def __init__(self):
        self.status_calls = []
        self.delete_calls = []

    def set_torrents_status(self, **kwargs):
        self.status_calls.append(kwargs)

    def delete_torrents(self, **kwargs):
        self.delete_calls.append(kwargs)


class _FakeFactory:
    def __init__(self, client: _FakeClient):
        self.client = client

    def get_client(self, _downloader_id):
        return self.client


class _FakePipeline:
    def __init__(self, success: bool = True):
        self.success = success
        self.tasks: list[Any] = []

    def process(self, task):
        self.tasks.append(task)
        message = "boom" if not self.success else "ok"
        task.post_process(task, self.success, message)
        return self.success, message


def test_transfer_queue_executes_and_post_processes(monkeypatch):
    monkeypatch.setattr(module, "create_task_queue", lambda name: MemoryTaskQueue(name))
    client = _FakeClient()
    pipeline = _FakePipeline()
    service = TransferQueueService(pipeline, _FakeFactory(client), max_workers=1)
    payload = {
        "downloader_id": "4",
        "task_id": "task-1",
        "path": "/downloads/Demo",
        "name": "Thunder",
        "tags": "demo",
        "operation": "copy",
        "target_dir": "/media",
        "unknown_dir": "/unknown",
        "provider_data": {"title": "Demo"},
        "media_type": "movie",
        "season": None,
        "fallback_episode": None,
    }
    assert service.submit(payload)
    _wait_until(lambda: len(pipeline.tasks) == 1)
    task = pipeline.tasks[0]
    assert task.source_type.value == "downloader"
    assert task.file_paths == ["/downloads/Demo"]
    _wait_until(lambda: bool(client.status_calls))
    assert client.status_calls[0]["ids"] == "task-1"
    service.stop()


def test_transfer_queue_failure_keeps_status_for_retry(monkeypatch):
    monkeypatch.setattr(module, "create_task_queue", lambda name: MemoryTaskQueue(name))
    client = _FakeClient()
    pipeline = _FakePipeline(success=False)
    service = TransferQueueService(pipeline, _FakeFactory(client), max_workers=1)
    service.submit(
        {
            "downloader_id": "4",
            "task_id": "task-2",
            "path": "/downloads/Demo",
            "name": "Thunder",
            "tags": "demo",
            "operation": "copy",
        }
    )
    _wait_until(lambda: len(pipeline.tasks) >= 1)
    assert client.status_calls == []
    service.stop()


def test_library_done_requires_exact_episode(monkeypatch):
    import app.services.transfer_queue_service as module

    repo = MagicMock()
    repo.get_current.return_value = None
    repo.get_grouped_identity.return_value = {
        "STAGE": "in_library",
        "STATUS": "succeeded",
    }
    monkeypatch.setattr(module, "LifecycleRepository", lambda: repo)
    service = TransferQueueService(_FakePipeline(), _FakeFactory(_FakeClient()))

    assert service._is_library_done({"identity_id": "x", "season": 1, "episode": 2}) is False
    assert service._is_library_done({"identity_id": "x"}) is True


def test_submit_skips_terminal_dedup_task():
    queue = MagicMock()
    task = Task.create("transfer", "transfer.task", {})
    task.status = TaskStatus.SUCCEEDED
    queue.enqueue.return_value = task
    lifecycle = MagicMock()
    service = TransferQueueService(_FakePipeline(), _FakeFactory(_FakeClient()), lifecycle=lifecycle)
    service._queue = queue

    assert service.submit({"downloader_id": "4", "task_id": "task-done"})
    lifecycle.record.assert_not_called()


def _wait_until(predicate, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition not met in time")

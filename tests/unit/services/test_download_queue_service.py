"""下载队列服务测试."""

from __future__ import annotations

import time
from typing import Any

from app.domain.mediatypes import MediaType
from app.infrastructure.task_queue.memory_queue import MemoryTaskQueue
from app.media.models import MediaInfo
from app.services import download_queue_service as dq_module
from app.services.download_queue_service import DownloadQueueService


class _FakePipeline:
    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    def execute(self, **kwargs):
        self.calls.append(kwargs)
        return kwargs["downloader_id"], "real-download-id", ""


class _FakeClient:
    def __init__(self):
        self.active: list[Any] = []

    def get_downloading_torrents(self):
        return list(self.active)


class _FakeFactory:
    def __init__(self, ctype: str = "thunder", client: _FakeClient | None = None):
        self.ctype = ctype
        self.client = client or _FakeClient()

    def get_downloader_conf(self, _downloader_id):
        return {"type": self.ctype, "config": {}, "name": "demo"}

    def get_client(self, _downloader_id):
        return self.client


class _FakeHistory:
    def __init__(self):
        self.inserted: list[dict[str, Any]] = []
        self.updated: list[tuple] = []
        self.deleted: list[int] = []

    def insert_download_history(self, **kwargs):
        self.inserted.append(kwargs)
        return 11

    def get_download_history_by_row_id(self, history_id):
        return None

    def update_download_history_task(self, history_id, download_id, save_dir, state="downloading"):
        self.updated.append((history_id, download_id, save_dir, state))
        return True

    def delete_download_history_by_id(self, history_id):
        self.deleted.append(history_id)
        return True


def _media():
    return MediaInfo(
        type=MediaType.MOVIE,
        title="Demo",
        org_string="DEMO-001",
        enclosure="magnet:?xt=urn:btih:abc123",
    )


def test_thunder_movie_uses_queue_and_updates_history(monkeypatch):
    monkeypatch.setattr(dq_module, "create_task_queue", lambda _name: MemoryTaskQueue("download:4"))
    history = _FakeHistory()
    pipeline = _FakePipeline()
    service = DownloadQueueService(pipeline, _FakeFactory(), history)

    task = service.submit(_media(), downloader_id="4")
    assert task is not None
    assert history.inserted and history.inserted[0]["state"] == "queued"

    _wait_until(lambda: len(pipeline.calls) == 1)
    assert pipeline.calls[0]["history_id"] == 11
    assert pipeline.calls[0]["downloader_id"] == "4"

    stack = service._stacks["4"]
    stack[1].stop()


def test_qbittorrent_does_not_use_nexus_queue():
    service = DownloadQueueService(_FakePipeline(), _FakeFactory("qbittorrent"), _FakeHistory())
    assert not service.should_queue(_media(), "1")


def test_thunder_max_active_defaults_to_five():
    service = DownloadQueueService(_FakePipeline(), _FakeFactory("thunder"), _FakeHistory())
    assert service._max_active("4") == 5


def _wait_until(predicate, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition not met in time")


def test_download_core_returns_queued_task_without_calling_pipeline():
    from threading import Lock
    from unittest.mock import MagicMock

    from app.infrastructure.task_queue.models import Task
    from app.services.download_core import DownloadCore

    core = DownloadCore.__new__(DownloadCore)
    core._pipeline = MagicMock()
    core._pipeline.resolve_downloader_id.return_value = "4"
    core._pipeline.execute = MagicMock(side_effect=AssertionError("不应直接执行流水线"))
    core._download_fail_cache = MagicMock()
    core._download_fail_cache.get.return_value = None
    core._link_locks = {}
    core._link_locks_guard = Lock()
    queue_service = MagicMock()
    queue_service.should_queue.return_value = True
    queue_service.submit.return_value = Task.create("download:4", "download.add", {})
    core._download_queue = queue_service

    media = MediaInfo(type=MediaType.MOVIE, title="Demo")
    result = core.download(media)

    assert result[0] == "4"
    assert result[1] == queue_service.submit.return_value.id
    queue_service.submit.assert_called_once()
    core._pipeline.execute.assert_not_called()


def test_download_core_fails_closed_when_managed_queue_unavailable():
    from threading import Lock
    from unittest.mock import MagicMock

    from app.infrastructure.task_queue.models import QueueUnavailableError
    from app.services.download_core import DownloadCore

    core = DownloadCore.__new__(DownloadCore)
    core._pipeline = MagicMock()
    core._pipeline.resolve_downloader_id.return_value = "4"
    core._pipeline.execute = MagicMock(side_effect=AssertionError("不应绕过队列"))
    core._download_fail_cache = MagicMock()
    core._download_fail_cache.get.return_value = None
    core._link_locks = {}
    core._link_locks_guard = Lock()
    queue_service = MagicMock()
    queue_service.should_queue.return_value = True
    queue_service.submit.side_effect = QueueUnavailableError("redis down")
    core._download_queue = queue_service

    result = core.download(MediaInfo(type=MediaType.MOVIE, title="Demo"))

    assert result[1] is None
    assert "下载队列不可用" in result[2]
    core._pipeline.execute.assert_not_called()

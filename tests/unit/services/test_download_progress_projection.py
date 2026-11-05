"""下载进度投影到生命周期测试."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

from app.domain.lifecycle import LifecycleStage, LifecycleStatus
from app.services.download_service import DownloadService


def _service():
    svc = object.__new__(DownloadService)
    svc._lifecycle = MagicMock()
    lifecycle = cast(MagicMock, svc._lifecycle)
    svc._progress_reported = {}
    return svc, lifecycle


def _task():
    return SimpleNamespace(
        id=1,
        download_id="abc",
        title="Demo",
        torrent="Demo.torrent",
        year="2024",
        tmdb_id="123",
        media_type="movie",
        anchor_provider=None,
        anchor_external_id=None,
        identity_id="id-1",
        content_profile="default",
    )


class TestDownloadProgressProjection:
    def test_projects_progress_in_ten_percent_steps(self):
        svc, lifecycle = _service()

        svc._project_download_progress(_task(), 33)
        svc._project_download_progress(_task(), 37)
        svc._project_download_progress(_task(), 45)

        assert lifecycle.record_media.call_count == 2
        first = lifecycle.record_media.call_args_list[0].kwargs
        assert first["stage"] == LifecycleStage.DOWNLOADING
        assert first["status"] == LifecycleStatus.RUNNING
        assert first["progress"] == 33
        assert first["event_key"] == "download:abc"

    def test_invalid_progress_ignored(self):
        svc, lifecycle = _service()

        svc._project_download_progress(_task(), "n/a")

        lifecycle.record_media.assert_not_called()

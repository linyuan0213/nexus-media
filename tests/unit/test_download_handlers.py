"""下载领域事件处理器单元测试."""

import queue

from app.events import Event
from app.events.constants import DOWNLOAD_COMPLETED, DOWNLOAD_FAILED, DOWNLOAD_STARTED
from app.events.payloads import DownloadCompletedPayload, DownloadFailedPayload, DownloadStartedPayload


def _drain(q):
    while True:
        try:
            q.get_nowait()
        except queue.Empty:
            break


class TestDownloadHandlers:
    def test_handle_download_started_pushes_to_queue(self):
        from app.services.download.handlers import handle_download_started
        from app.services.download_event_queue import download_event_queue

        _drain(download_event_queue)

        event = Event(
            event_type=DOWNLOAD_STARTED,
            payload=DownloadStartedPayload(
                media_info={"title": "Test Movie"},
                is_paused=False,
                tag="NEXUS_MEDIA",
                download_dir="/dl",
                download_setting=1,
                downloader_id="qb1",
                torrent_file="/tmp/test.torrent",
                download_id="abc123",
            ),
        )
        handle_download_started(event)

        item = download_event_queue.get(timeout=1)
        assert item["event"] == DOWNLOAD_STARTED
        assert item["data"]["title"] == "Test Movie"
        assert item["data"]["downloader_id"] == "qb1"
        assert item["data"]["download_id"] == "abc123"

    def test_handle_download_failed_pushes_to_queue(self):
        from app.services.download.handlers import handle_download_failed
        from app.services.download_event_queue import download_event_queue

        _drain(download_event_queue)

        event = Event(
            event_type=DOWNLOAD_FAILED,
            payload=DownloadFailedPayload(media_info={"title": "Test Movie"}, reason="连接超时"),
        )
        handle_download_failed(event)

        item = download_event_queue.get(timeout=1)
        assert item["event"] == DOWNLOAD_FAILED
        assert item["data"]["title"] == "Test Movie"
        assert item["data"]["reason"] == "连接超时"

    def test_handle_download_completed_pushes_to_queue(self):
        from app.services.download.handlers import handle_download_completed
        from app.services.download_event_queue import download_event_queue

        _drain(download_event_queue)

        event = Event(
            event_type=DOWNLOAD_COMPLETED,
            payload=DownloadCompletedPayload(
                downloader_id="qb1",
                task_id="task123",
                path="/dl/movie.mkv",
                tags=["NEXUS_MEDIA"],
                name="movie",
            ),
        )
        handle_download_completed(event)

        item = download_event_queue.get(timeout=1)
        assert item["event"] == DOWNLOAD_COMPLETED
        assert item["data"]["downloader_id"] == "qb1"
        assert item["data"]["task_id"] == "task123"
        assert item["data"]["path"] == "/dl/movie.mkv"
        assert item["data"]["tags"] == ["NEXUS_MEDIA"]
        assert item["data"]["name"] == "movie"

    def test_handle_download_started_with_dict_payload(self):
        """payload 是 dict 时也能正常处理."""
        from app.services.download.handlers import handle_download_started
        from app.services.download_event_queue import download_event_queue

        _drain(download_event_queue)

        event = Event(
            event_type=DOWNLOAD_STARTED,
            payload={
                "media_info": {"title": "Dict Movie"},
                "is_paused": False,
                "tag": None,
                "download_dir": None,
                "download_setting": None,
                "downloader_id": None,
                "torrent_file": None,
                "download_id": "dict123",
            },
        )
        handle_download_started(event)

        item = download_event_queue.get(timeout=1)
        assert item["data"]["title"] == "Dict Movie"
        assert item["data"]["download_id"] == "dict123"

    def test_handle_download_completed_with_dict_payload(self):
        """payload 是 dict 时也能正常处理."""
        from app.services.download.handlers import handle_download_completed
        from app.services.download_event_queue import download_event_queue

        _drain(download_event_queue)

        event = Event(
            event_type=DOWNLOAD_COMPLETED,
            payload={
                "downloader_id": "qb1",
                "task_id": "task456",
                "path": "/dl/tv.mkv",
                "tags": None,
                "name": "tv show",
            },
        )
        handle_download_completed(event)

        item = download_event_queue.get(timeout=1)
        assert item["data"]["task_id"] == "task456"

    def test_handle_download_failed_with_dict_payload(self):
        """payload 是 dict 时也能正常处理."""
        from app.services.download.handlers import handle_download_failed
        from app.services.download_event_queue import download_event_queue

        _drain(download_event_queue)

        event = Event(
            event_type=DOWNLOAD_FAILED,
            payload={"media_info": {"title": "Bad Movie"}, "reason": "网络错误"},
        )
        handle_download_failed(event)

        item = download_event_queue.get(timeout=1)
        assert item["data"]["reason"] == "网络错误"

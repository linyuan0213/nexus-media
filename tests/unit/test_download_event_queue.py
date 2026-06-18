"""下载事件队列单元测试."""

import queue

from app.services.download_event_queue import download_event_queue


class TestDownloadEventQueue:
    def test_queue_is_standard_queue(self):
        assert isinstance(download_event_queue, queue.Queue)

    def test_put_and_get(self):
        while not download_event_queue.empty():
            download_event_queue.get_nowait()

        download_event_queue.put({"event": "test", "data": {"k": "v"}})
        item = download_event_queue.get(timeout=1)

        assert item == {"event": "test", "data": {"k": "v"}}

    def test_get_blocks_on_empty(self):
        while not download_event_queue.empty():
            download_event_queue.get_nowait()

        try:
            download_event_queue.get(timeout=0.01)
            assert False, "should have raised"
        except queue.Empty:
            pass

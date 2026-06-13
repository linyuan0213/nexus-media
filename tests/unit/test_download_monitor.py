"""DownloadMonitor 单元测试."""

from unittest.mock import MagicMock, patch

import pytest

from app.events import Event
from app.events.constants import DOWNLOAD_COMPLETED
from app.services.download_monitor import DownloadMonitor


class TestDownloadMonitor:
    """Test suite for DownloadMonitor."""

    @pytest.fixture
    def mock_factory(self):
        factory = MagicMock()
        factory.monitor_downloader_ids = ["qb1", "tr1"]
        return factory

    @pytest.fixture
    def mock_bus(self):
        return MagicMock()

    @pytest.fixture
    def monitor(self, mock_factory, mock_bus):
        m = DownloadMonitor(
            client_factory=mock_factory,
            event_bus=mock_bus,
            interval=1,
            max_workers=2,
        )
        return m, mock_factory, mock_bus

    def test_init(self, monitor):
        m, factory, bus = monitor
        assert m._interval == 1
        assert m._max_workers == 2
        assert m._running is False

    def test_make_id(self, monitor):
        m, _, _ = monitor
        assert m._make_id("qb1", "abc123") == "qb1:abc123"

    def test_warmup(self, monitor):
        m, factory, _ = monitor

        mock_client = MagicMock()
        mock_torrent = MagicMock()
        mock_torrent.id = "task1"
        mock_client.get_torrents.return_value = ([mock_torrent], False)
        factory.get_client.return_value = mock_client

        m._warmup()
        assert "qb1:task1" in m._processed_ids
        assert "tr1:task1" in m._processed_ids

    def test_warmup_no_client(self, monitor):
        m, factory, _ = monitor
        factory.get_client.return_value = None
        m._warmup()
        assert len(m._processed_ids) == 0

    def test_check_downloader_new_task(self, monitor):
        m, factory, bus = monitor

        mock_client = MagicMock()
        mock_client.get_transfer_task.return_value = [
            {"id": "task1", "path": "/dl/movie.mkv", "tags": ["NEXUS_MEDIA"], "name": "movie"}
        ]
        factory.get_client.return_value = mock_client
        factory.get_downloader_conf.return_value = {"name": "QB", "only_nexus_media": True}

        m._check_downloader("qb1")

        bus.publish.assert_called_once()
        event = bus.publish.call_args[0][0]
        assert isinstance(event, Event)
        assert event.event_type == DOWNLOAD_COMPLETED
        assert event.payload.task_id == "task1"
        assert "qb1:task1" in m._processed_ids

    def test_check_downloader_duplicate_task(self, monitor):
        m, factory, bus = monitor

        m._processed_ids.add("qb1:task1")

        mock_client = MagicMock()
        mock_client.get_transfer_task.return_value = [{"id": "task1", "path": "/dl/movie.mkv", "tags": ["NEXUS_MEDIA"]}]
        factory.get_client.return_value = mock_client
        factory.get_downloader_conf.return_value = {"name": "QB", "only_nexus_media": True}

        m._check_downloader("qb1")
        bus.publish.assert_not_called()

    def test_check_downloader_no_tasks(self, monitor):
        m, factory, bus = monitor

        mock_client = MagicMock()
        mock_client.get_transfer_task.return_value = []
        factory.get_client.return_value = mock_client
        factory.get_downloader_conf.return_value = {"name": "QB"}

        m._check_downloader("qb1")
        bus.publish.assert_not_called()

    def test_check_downloader_no_conf(self, monitor):
        m, factory, bus = monitor
        factory.get_downloader_conf.return_value = None
        m._check_downloader("qb1")
        bus.publish.assert_not_called()

    def test_mark_processed(self, monitor):
        m, _, _ = monitor
        m.mark_processed("qb1", "task99")
        assert "qb1:task99" in m._processed_ids

    def test_start_stop(self, monitor):
        m, _, _ = monitor
        with patch.object(m, "_warmup"):
            with patch.object(m, "_monitor_loop"):
                m.start()
                assert m._running is True
                assert m._executor is not None
                m.stop()
                assert m._running is False

    def test_check_multiple_downloaders(self, monitor):
        """测试逐个检查多个下载器."""
        m, factory, bus = monitor

        def mock_client_for_did(did):
            client = MagicMock()
            client.get_transfer_task.return_value = [
                {"id": f"task_{did}", "path": f"/dl/{did}.mkv", "tags": [], "name": did}
            ]
            return client

        factory.get_client.side_effect = mock_client_for_did
        factory.get_downloader_conf.return_value = {"name": "Test"}

        m._check_downloader("qb1")
        m._check_downloader("tr1")

        assert bus.publish.call_count == 2
        assert "qb1:task_qb1" in m._processed_ids
        assert "tr1:task_tr1" in m._processed_ids

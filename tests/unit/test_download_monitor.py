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
        mock_client.get_transfer_task.return_value = [
            {"id": "task1", "path": "/dl/movie.mkv", "tags": [], "name": "movie"}
        ]
        factory.get_client.return_value = mock_client
        factory.get_downloader_conf.return_value = {
            "only_nexus_media": False,
            "match_path": False,
        }

        m._warmup()
        assert "qb1:task1" in m._processed_ids
        assert "tr1:task1" in m._processed_ids

    def test_warmup_no_client(self, monitor):
        m, factory, _ = monitor
        factory.get_client.return_value = None
        factory.get_downloader_conf.return_value = {
            "only_nexus_media": False,
            "match_path": False,
        }
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

    def test_check_downloader_initial_full_scan(self, monitor):
        """首次检查应全量拉取并建立快照."""
        m, factory, bus = monitor

        mock_client = MagicMock()
        mock_client.get_transfer_task.return_value = [
            {"id": "task1", "path": "/dl/movie.mkv", "tags": ["NEXUS_MEDIA"], "name": "movie"}
        ]
        factory.get_client.return_value = mock_client
        factory.get_downloader_conf.return_value = {"name": "QB", "only_nexus_media": True}

        m._check_downloader("qb1")

        assert m._last_snapshot["qb1"] == {"task1"}
        bus.publish.assert_called_once()
        assert mock_client.get_transfer_task.call_args_list == [
            (({"tag": "NEXUS_MEDIA", "match_path": None}),),
        ]

    def test_check_downloader_incremental_only_new_tasks(self, monitor):
        """后续检查只拉取新增任务."""
        m, factory, bus = monitor
        m._last_snapshot["qb1"] = {"task1"}

        mock_client = MagicMock()
        mock_client.get_transfer_task.side_effect = [
            # 第一次返回全部候选 id
            [
                {"id": "task1", "path": "/dl/movie.mkv", "tags": ["NEXUS_MEDIA"]},
                {"id": "task2", "path": "/dl/new.mkv", "tags": ["NEXUS_MEDIA"]},
            ],
            # 第二次只返回新增任务详情
            [{"id": "task2", "path": "/dl/new.mkv", "tags": ["NEXUS_MEDIA"]}],
        ]
        factory.get_client.return_value = mock_client
        factory.get_downloader_conf.return_value = {"name": "QB", "only_nexus_media": True}

        m._check_downloader("qb1")

        assert m._last_snapshot["qb1"] == {"task1", "task2"}
        assert bus.publish.call_count == 1
        event = bus.publish.call_args[0][0]
        assert event.payload.task_id == "task2"
        assert mock_client.get_transfer_task.call_count == 2
        assert mock_client.get_transfer_task.call_args == (
            (),
            {"tag": "NEXUS_MEDIA", "match_path": None, "ids": ["task2"]},
        )

    def test_check_downloader_no_new_tasks(self, monitor):
        """无新增任务时不发布事件."""
        m, factory, bus = monitor
        m._last_snapshot["qb1"] = {"task1"}

        mock_client = MagicMock()
        mock_client.get_transfer_task.return_value = [
            {"id": "task1", "path": "/dl/movie.mkv", "tags": ["NEXUS_MEDIA"]},
        ]
        factory.get_client.return_value = mock_client
        factory.get_downloader_conf.return_value = {"name": "QB", "only_nexus_media": True}

        m._check_downloader("qb1")

        assert m._last_snapshot["qb1"] == {"task1"}
        bus.publish.assert_not_called()
        mock_client.get_transfer_task.assert_called_once_with(tag="NEXUS_MEDIA", match_path=None)

    def test_emit_new_tasks_filters_processed(self, monitor):
        """_emit_new_tasks 不会重复发布已处理任务."""
        m, _, bus = monitor
        m._processed_ids.add("qb1:task1")

        m._emit_new_tasks(
            "qb1",
            [
                {"id": "task1", "path": "/dl/old.mkv"},
                {"id": "task2", "path": "/dl/new.mkv"},
            ],
        )

        assert bus.publish.call_count == 1
        event = bus.publish.call_args[0][0]
        assert event.payload.task_id == "task2"
        assert "qb1:task2" in m._processed_ids

    def test_emit_new_tasks_skips_empty_path_or_id(self, monitor):
        """_emit_new_tasks 跳过空 id 或空 path 的任务."""
        m, _, bus = monitor

        m._emit_new_tasks(
            "qb1",
            [
                {"id": "", "path": "/dl/a.mkv"},
                {"id": "task2", "path": ""},
                {"id": "task3", "path": "/dl/c.mkv"},
            ],
        )

        assert bus.publish.call_count == 1
        event = bus.publish.call_args[0][0]
        assert event.payload.task_id == "task3"

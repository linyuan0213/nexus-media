import pytest
from unittest.mock import MagicMock

from app.schemas.brush import BrushTaskDTO, BrushTorrentListDTO
from app.services.brush_service import BrushService


@pytest.fixture
def svc():
    mock_brush = MagicMock()
    return BrushService(brush_task=mock_brush)


class TestBuildTaskItem:
    def test_basic(self, svc):
        data = {
            "brushtask_name": "Task1",
            "brushtask_site": "site1",
            "brushtask_totalsize": "10",
            "brushtask_transfer": True,
            "brushtask_sendmessage": False,
            "brushtask_free": "Y",
            "brushtask_hr": "N",
            "brushtask_torrent_size": "",
            "brushtask_include": "",
            "brushtask_exclude": "",
            "brushtask_dlcount": "",
            "brushtask_peercount": "",
            "brushtask_pubdate": "",
            "brushtask_upspeed": "",
            "brushtask_downspeed": "",
            "brushtask_exclude_subscribe": "",
            "brushtask_mode": "",
            "brushtask_seedtime": "",
            "brushtask_hr_seedtime": "",
            "brushtask_seedratio": "",
            "brushtask_seedsize": "",
            "brushtask_dltime": "",
            "brushtask_avg_upspeed": "",
            "brushtask_iatime": "",
            "brushtask_pending_time": "",
            "brushtask_freespace": "",
            "brushtask_freestatus": "",
            "brushtask_stopfree": True,
        }
        item = svc.build_task_item(data)
        assert item["name"] == "Task1"
        assert item["transfer"] == 'Y'
        assert item["sendmessage"] == 'N'
        assert item["seed_size"] == 10 * 1024 ** 3
        assert item["rss_rule"]["free"] == "Y"
        assert item["stop_rule"]["stopfree"] == 'Y'

    def test_invalid_size(self, svc):
        data = {"brushtask_totalsize": "abc"}
        item = svc.build_task_item(data)
        assert item["seed_size"] == 0


class TestAddOrUpdateTask:
    def test_ok(self, svc):
        svc.add_or_update_task({
            "brushtask_id": 1,
            "brushtask_name": "T",
            "brushtask_totalsize": "",
            "brushtask_transfer": False,
            "brushtask_sendmessage": False,
            "brushtask_free": "", "brushtask_hr": "",
            "brushtask_torrent_size": "", "brushtask_include": "",
            "brushtask_exclude": "", "brushtask_dlcount": "",
            "brushtask_peercount": "", "brushtask_pubdate": "",
            "brushtask_upspeed": "", "brushtask_downspeed": "",
            "brushtask_exclude_subscribe": "",
            "brushtask_mode": "", "brushtask_seedtime": "",
            "brushtask_hr_seedtime": "", "brushtask_seedratio": "",
            "brushtask_seedsize": "", "brushtask_dltime": "",
            "brushtask_avg_upspeed": "", "brushtask_iatime": "",
            "brushtask_pending_time": "", "brushtask_freespace": "",
            "brushtask_freestatus": "", "brushtask_stopfree": False,
        })
        svc._brush.update_brushtask.assert_called_once()


class TestGetTask:
    def test_found(self, svc):
        svc._brush.get_brushtask_info.return_value = {"id": 1}
        dto = svc.get_task(1)
        assert dto.task == {"id": 1}

    def test_not_found(self, svc):
        svc._brush.get_brushtask_info.return_value = None
        dto = svc.get_task(1)
        assert dto.task is None


class TestGetTasks:
    def test_ok(self, svc):
        svc._brush.get_brushtask_info.return_value = [{"id": 1}]
        assert svc.get_tasks() == [{"id": 1}]


class TestDeleteTask:
    def test_ok(self, svc):
        svc.delete_task(1)
        svc._brush.delete_brushtask.assert_called_once_with(1)


class TestGetTorrents:
    def test_with_results(self, svc):
        mock_t = MagicMock()
        mock_t.as_dict.return_value = {"id": 1}
        svc._brush.get_brushtask_torrents.return_value = [mock_t]
        dto = svc.get_torrents(1)
        assert dto.torrents == [{"id": 1}]

    def test_empty(self, svc):
        svc._brush.get_brushtask_torrents.return_value = []
        dto = svc.get_torrents(1)
        assert dto.torrents is None


class TestRunTask:
    def test_ok(self, svc):
        svc.run_task(1)
        svc._brush.check_task_rss.assert_called_once_with(1)


class TestUpdateTaskState:
    def test_with_ids(self, svc):
        svc.update_task_state("R", [1, 2])
        assert svc._brush.update_brushtask_state.call_count == 2

    def test_all(self, svc):
        svc.update_task_state("R", None)
        svc._brush.update_brushtask_state.assert_called_once_with(state="R")

    def test_none(self, svc):
        svc.update_task_state(None, [1])
        svc._brush.update_brushtask_state.assert_not_called()

"""多实例媒体库 API 契约测试。"""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

from api.routers.media import (
    LibraryTargetRequest,
    RefreshLibraryRequest,
    StartMediasyncRequest,
    get_library_home,
    refresh_library,
    start_mediasync,
)
from app.services.media_library_service import MediaLibraryService


class _Service:
    def get_servers(self):
        return [
            {"id": 1, "name": "普通 Emby", "type": "emby", "is_default": True},
            {"id": 2, "name": "演示 Emby", "type": "emby", "is_default": False},
        ]

    def get_media_count(self, server_id):
        return {"Movie": "3" if server_id == 1 else "5", "Series": "2", "User": "1"}

    def get_libraries(self, server_id):
        return [{"id": f"lib-{server_id}", "name": "库"}]

    def get_resume(self, server_id=None):
        return [{"id": f"resume-{server_id}"}]

    def get_latest(self, server_id=None):
        return [{"id": f"latest-{server_id}"}]

    def get_play_history(self, server_id):
        return [
            {
                "id": f"activity-{server_id}",
                "date": "2024-01-01 00:00:00" if server_id == 1 else "2026-01-01 00:00:00",
            }
        ]

    def get_sync_state(self, server_id):
        return f"实例 {server_id} 已同步"

    def get_home_data(self, requested_id=None):
        manager = MagicMock()
        manager.get_server_options.side_effect = self.get_servers
        manager.get_medias_count.side_effect = lambda server_id: {
            "MovieCount": 3 if server_id == 1 else 5,
            "SeriesCount": 2,
            "EpisodeCount": 0,
            "SongCount": 0,
        }
        manager.get_user_count.return_value = 1
        manager.get_libraries.side_effect = self.get_libraries
        manager.get_resume.side_effect = self.get_resume
        manager.get_latest.side_effect = self.get_latest
        manager.get_activity_log.side_effect = lambda limit, server_id: self.get_play_history(server_id)
        manager.get_mediasync_status.side_effect = lambda server_id: {
            "movie_count": 1,
            "tv_count": 1,
            "time": "2026-01-01 00:00:00",
        }
        filetransfer = MagicMock()
        filetransfer.get_default_local_path.return_value = "/tmp"
        service = MediaLibraryService(manager, filetransfer, MagicMock(), MagicMock(), MagicMock())
        return service.get_home_data(requested_id)

    def get_space_info(self):
        return SimpleNamespace(used_percent=50, free_space="50G", used_space="50G", total_space="100G")


def test_home_returns_independent_sections_and_legacy_aggregates():
    response = get_library_home(None, current_user=MagicMock(), svc=cast(Any, _Service()))
    data = response["data"]
    assert len(data["sections"]) == 2
    assert data["media_counts"]["Movie"] == 8
    assert data["media_counts"]["Series"] == 4
    assert data["sections"][1]["server_name"] == "演示 Emby"
    assert data["sections"][1]["librarys"][0]["server_id"] == 2
    assert data["sections"][1]["sync_state"].startswith("电影")
    assert data["activitys"][0]["id"] == "activity-2"


def test_home_filters_one_instance():
    response = get_library_home(LibraryTargetRequest(server_id=2), current_user=MagicMock(), svc=cast(Any, _Service()))
    data = response["data"]
    assert len(data["sections"]) == 1
    assert data["sections"][0]["server_id"] == 2
    assert data["media_counts"]["Movie"] == 5
    assert len(data["servers"]) == 2


def test_refresh_and_sync_accept_target_instance():
    svc = MagicMock()
    refresh_library(
        RefreshLibraryRequest(server_id=2),
        current_user=MagicMock(),
        svc=svc,
    )
    svc.refresh_library.assert_called_once_with(server_id=2, items=None)

    start_mediasync(
        StartMediasyncRequest(server_id=2, librarys=["lib-demo"]),
        current_user=MagicMock(),
        svc=svc,
    )
    svc.start_sync.assert_called_once_with(librarys=["lib-demo"], server_id=2)

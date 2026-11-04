"""媒体服务器多实例管理与定向刷新测试。"""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

from app.mediaserver.media_server import MediaServer


def _row(sid, name, server_type="emby", default=False):
    return SimpleNamespace(
        ID=sid,
        NAME=name,
        TYPE=server_type,
        ENABLED=1,
        IS_DEFAULT=int(default),
        CONFIG=f'{{"host":"http://server-{sid}"}}',
    )


def _server(rows):
    config_repo = MagicMock()
    config_repo.get_media_servers.side_effect = lambda sid=None: ([row for row in rows if sid is None or row.ID == sid])
    config_repo.get_default_media_server.return_value = next((row for row in rows if row.IS_DEFAULT), None)
    route_repo = MagicMock()
    server = MediaServer(
        media_service=MagicMock(),
        message=MagicMock(),
        message_queue=MagicMock(),
        media_sync_repo=MagicMock(),
        progress_helper=MagicMock(),
        system_config=MagicMock(),
        media_server_repo=config_repo,
        route_repo=route_repo,
    )
    return server, route_repo


def test_clients_are_cached_per_instance():
    rows = [_row(1, "普通 Emby", default=True), _row(2, "演示 Emby")]
    server, _ = _server(rows)
    clients = {1: MagicMock(), 2: MagicMock()}

    with patch.object(
        MediaServer,
        "_MediaServer__get_server",
        side_effect=lambda ctype, conf: clients[int(conf["host"].rsplit("-", 1)[1])],
    ) as build:
        assert server._get_client(1) is clients[1]
        assert server._get_client(2) is clients[2]
        assert server._get_client(2) is clients[2]
        assert build.call_count == 2


def test_disabled_default_instance_is_not_used():
    row = _row(1, "默认 Emby", default=True)
    row.ENABLED = 0
    server, _ = _server([row])
    assert server._get_client() is None


def test_profile_refresh_uses_routed_instance():
    rows = [_row(1, "普通 Emby", default=True), _row(2, "演示 Emby")]
    server, route_repo = _server(rows)
    route_repo.get_profile.return_value = SimpleNamespace(server_id=2, library_id=None)
    clients = {1: MagicMock(), 2: MagicMock()}
    lock = MagicMock()
    lock.acquire.return_value = True

    with (
        patch.object(
            MediaServer,
            "_MediaServer__get_server",
            side_effect=lambda ctype, conf: clients[int(conf["host"].rsplit("-", 1)[1])],
        ),
        patch("app.mediaserver.media_server.get_lock_manager") as lock_manager,
    ):
        lock_manager.return_value.create_lock.return_value = lock
        server.refresh_library_by_items([{"title": "A", "content_profile": "demo"}])

    clients[2].refresh_library_by_items.assert_called_once()
    clients[1].refresh_library_by_items.assert_not_called()


def test_directory_refresh_uses_longest_path_and_groups():
    rows = [_row(1, "普通 Emby", default=True), _row(2, "演示 Emby")]
    server, route_repo = _server(rows)
    route_repo.list.return_value = [
        SimpleNamespace(enabled=True, target_path="/media", content_profile="", server_id=1, library_id=None),
        SimpleNamespace(enabled=True, target_path="/media/demo", content_profile="", server_id=2, library_id="4"),
    ]
    clients = {1: MagicMock(), 2: MagicMock()}
    lock = MagicMock()
    lock.acquire.return_value = True

    with (
        patch.object(
            MediaServer,
            "_MediaServer__get_server",
            side_effect=lambda ctype, conf: clients[int(conf["host"].rsplit("-", 1)[1])],
        ),
        patch("app.mediaserver.media_server.get_lock_manager") as lock_manager,
    ):
        lock_manager.return_value.create_lock.return_value = lock
        server.refresh_library_by_items(
            [
                {"title": "普通", "target_path": "/media/normal/movie"},
                {"title": "演示", "target_path": "/media/demo/movie"},
            ]
        )

    normal_items = clients[1].refresh_library_by_items.call_args.args[0]
    demo_items = clients[2].refresh_library_by_items.call_args.args[0]
    assert [item["title"] for item in normal_items] == ["普通"]
    assert [item["title"] for item in demo_items] == ["演示"]
    assert demo_items[0]["library_id"] == "4"


def test_directory_refresh_matches_route_without_content_profile():
    rows = [_row(1, "普通 Emby", default=True), _row(2, "演示 Emby")]
    server, route_repo = _server(rows)
    route_repo.list.return_value = [
        SimpleNamespace(
            enabled=True,
            target_path="/Media/private",
            content_profile="private",
            server_id=2,
            library_id=None,
        )
    ]
    clients = {1: MagicMock(), 2: MagicMock()}
    lock = MagicMock()
    lock.acquire.return_value = True

    with (
        patch.object(
            MediaServer,
            "_MediaServer__get_server",
            side_effect=lambda ctype, conf: clients[int(conf["host"].rsplit("-", 1)[1])],
        ),
        patch("app.mediaserver.media_server.get_lock_manager") as lock_manager,
    ):
        lock_manager.return_value.create_lock.return_value = lock
        server.refresh_library_by_items([{"title": "PPR-012", "target_path": "/Media/private/PPR/PPR-012"}])

    clients[2].refresh_library_by_items.assert_called_once()
    clients[1].refresh_library_by_items.assert_not_called()


def test_refresh_with_scan_refreshes_item_and_library():
    rows = [_row(1, "普通 Emby", default=True), _row(2, "演示 Emby")]
    server, route_repo = _server(rows)
    route_repo.list.return_value = [
        SimpleNamespace(
            enabled=True,
            target_path="/Media/private",
            content_profile="private",
            server_id=2,
            library_id="4",
        )
    ]
    clients = {1: MagicMock(), 2: MagicMock()}
    lock = MagicMock()
    lock.acquire.return_value = True

    with (
        patch.object(
            MediaServer,
            "_MediaServer__get_server",
            side_effect=lambda ctype, conf: clients[int(conf["host"].rsplit("-", 1)[1])],
        ),
        patch("app.mediaserver.media_server.get_lock_manager") as lock_manager,
    ):
        lock_manager.return_value.create_lock.return_value = lock
        server.refresh_library_with_scan([{"title": "X", "target_path": "/Media/private/X"}])

    clients[2].refresh_library_by_items.assert_called_once()
    clients[2].refresh_library.assert_called_once_with("4")
    clients[1].refresh_library_by_items.assert_not_called()


@patch("app.mediaserver.media_server.get_lock_manager")
def test_sync_only_clears_target_instance(lock_manager):
    lock = MagicMock()
    lock.acquire.return_value = True
    lock_manager.return_value.create_lock.return_value = lock
    rows = [_row(1, "普通 Emby", default=True), _row(2, "演示 Emby")]
    server, _ = _server(rows)
    server._server = MagicMock()
    server._get_client = MagicMock(return_value=server._server)
    server.get_medias_count = MagicMock(return_value={"MovieCount": 1, "SeriesCount": 0})
    server.get_libraries = MagicMock(return_value=[{"id": "lib-demo", "name": "演示"}])
    server.get_items = MagicMock(return_value=[{"id": "movie-1", "library": "lib-demo", "type": "Movie", "title": "A"}])

    server.sync_mediaserver(server_id=2, library_ids=["lib-demo"])

    repo = cast(Any, server.mediadb)
    repo.empty.assert_called_once_with(server_type="emby", server_id=2)
    _, kwargs = repo.statistics.call_args
    assert kwargs["server_id"] == 2
    assert kwargs["total_count"] == 1
    server.get_libraries.assert_called_once_with(2)
    server.get_items.assert_called_once_with("lib-demo", 2)

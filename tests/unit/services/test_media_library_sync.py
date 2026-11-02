"""媒体库同步配置持久化测试."""

from unittest.mock import MagicMock

from app.services.media_library_service import MediaLibraryService


def test_start_sync_persists_per_server_libraries():
    server = MagicMock()
    server.resolve_server_id.return_value = 3
    config = MagicMock()
    executor = MagicMock()
    svc = MediaLibraryService(
        media_server=server,
        filetransfer=MagicMock(),
        system_config=config,
        thread_executor=executor,
        media_config_service=MagicMock(),
        route_repo=MagicMock(),
    )

    svc.start_sync(["125861", "125862"], server_id=3)

    config.set.assert_any_call(key="SyncLibrary::3", value=["125861", "125862"])
    executor.submit.assert_called_once_with(server.sync_mediaserver, 3, ["125861", "125862"])

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.media_file_service import MediaFileService


def test_library_paths_include_content_profile_routes():
    route_repo = MagicMock()
    route_repo.list.return_value = [
        SimpleNamespace(
            id=1,
            content_profile="demo",
            target_path="/Media/demo",
            enabled=True,
            server_id=3,
            backend_id="2",
            library_id=None,
        )
    ]
    service = MediaFileService(
        event_bus=MagicMock(),
        storage_backend_repo=MagicMock(),
        media_service=MagicMock(),
        thread_executor=MagicMock(),
        scraper=MagicMock(),
        route_repo=route_repo,
    )

    result = service.get_library_paths(media={}, sync_svc=MagicMock(get_sync_paths=lambda: {}))

    item = next(item for item in result["library_paths"] if item["path"] == "/Media/demo")
    assert item["type"] == "demo"
    assert item["backend_id"] == "2"

"""入库通知归属解析测试（历史清理后按订阅反查）."""

from unittest.mock import MagicMock

from app.domain.mediatypes import MediaType
from app.services.transfer.filetransfer_service import FileTransferService


def _service(download_repo, subscribe_repo):
    return FileTransferService(
        media_service=MagicMock(),
        message=MagicMock(),
        scrape_queue_service=MagicMock(),
        thread_executor=MagicMock(),
        history_manager=MagicMock(),
        progress=MagicMock(),
        event_bus=MagicMock(),
        engine=MagicMock(),
        sync_path_repo=MagicMock(),
        path_resolver=MagicMock(),
        existence_checker=MagicMock(),
        cleanup_service=MagicMock(),
        download_repo=download_repo,
        subscribe_repo=subscribe_repo,
    )


def _tv_media():
    media = MagicMock()
    media.type = MediaType.TV
    media.tmdb_id = "308874"
    media.get_season_string.return_value = "S01"
    return media


class TestResolveOwnerUserId:
    def test_history_hit(self):
        download_repo = MagicMock()
        row = MagicMock()
        row.USER_ID = 5
        download_repo.get_download_history_by_path.return_value = row
        svc = _service(download_repo, MagicMock())
        assert svc._resolve_owner_user_id("/downloads/a.mkv", _tv_media()) == 5

    def test_fallback_to_tv_subscription(self):
        download_repo = MagicMock()
        download_repo.get_download_history_by_path.return_value = None
        subscribe_repo = MagicMock()
        subscribe_repo.find_tv_owner_user_id.return_value = 7
        svc = _service(download_repo, subscribe_repo)
        assert svc._resolve_owner_user_id("/downloads/gone.mkv", _tv_media()) == 7
        subscribe_repo.find_tv_owner_user_id.assert_called_once_with("308874", "S01")

    def test_fallback_to_movie_subscription(self):
        download_repo = MagicMock()
        download_repo.get_download_history_by_path.return_value = None
        subscribe_repo = MagicMock()
        subscribe_repo.find_movie_owner_user_id.return_value = 9
        svc = _service(download_repo, subscribe_repo)
        media = MagicMock()
        media.type = MediaType.MOVIE
        media.tmdb_id = "12345"
        assert svc._resolve_owner_user_id(None, media) == 9

    def test_unknown_owner_returns_none(self):
        download_repo = MagicMock()
        download_repo.get_download_history_by_path.return_value = None
        subscribe_repo = MagicMock()
        subscribe_repo.find_tv_owner_user_id.return_value = None
        svc = _service(download_repo, subscribe_repo)
        assert svc._resolve_owner_user_id("/x", _tv_media()) is None

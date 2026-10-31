"""TransferHistoryService 单元测试."""

from unittest.mock import MagicMock, call

import pytest

from app.services.transfer_history_service import TransferHistoryService


class _HistoryMock:
    def as_dict(self):
        return {
            "id": 1,
            "mode": "link",
            "source_path": "/src",
            "source_filename": "movie.mkv",
            "dest": "/dst",
        }


class _UnknownMock:
    ID: int = 10
    PATH: str | None = "C:\\unknown\\file.mkv"
    DEST: str = "C:\\dst"
    MODE: str = "copy"


@pytest.fixture
def mock_filetransfer():
    return MagicMock()


@pytest.fixture
def mock_sync_service():
    return MagicMock()


@pytest.fixture
def service(mock_filetransfer, mock_sync_service):
    svc = TransferHistoryService(
        filetransfer=mock_filetransfer,
        sync_service=mock_sync_service,
        cache_ttl=30,
    )
    svc._cache.clear()
    return svc


class TestTransferHistoryService:
    def test_get_transfer_history_page_defaults(self, service, mock_filetransfer):
        mock_filetransfer.get_transfer_history.return_value = None
        result = service.get_transfer_history_page("", None, None)
        assert result.total == 0
        assert result.result == []
        assert result.page_num == 30
        assert result.current_page == 1
        assert result.total_page == 1

    def test_get_transfer_history_page_with_data(self, service, mock_filetransfer):
        mock_filetransfer.get_transfer_history.return_value = (65, [_HistoryMock()])
        result = service.get_transfer_history_page("", 2, 20)
        assert result.total == 65
        assert result.current_page == 2
        assert result.page_num == 20
        assert result.total_page == 4
        assert result.result[0]["SYNC_MODE"] == "link"
        assert result.result[0]["RMT_MODE"] == "link"

    def test_history_capabilities_are_scoped_by_file_state(self, service, mock_filetransfer):
        class _DeletedSource:
            def as_dict(self):
                return {
                    "id": 9,
                    "mode": "link",
                    "source_path": "/src",
                    "source_filename": "movie.mkv",
                    "dest_path": "/dst",
                    "dest_filename": "movie.mkv",
                    "source_state": "deleted",
                    "dest_state": "present",
                }

        mock_filetransfer.get_transfer_history.return_value = (1, [_DeletedSource()])
        service._cache.clear()
        result = service.get_transfer_history_page("", 1, 20)

        item = result.result[0]
        assert item["SOURCE_STATE"] == "deleted"
        assert item["DEST_STATE"] == "present"
        assert item["CAPABILITIES"] == {
            "reidentify": False,
            "manual_identify": False,
            "delete_record": True,
            "delete_source": False,
            "delete_library": True,
        }

    def test_history_image_uses_local_poster(self, service, mock_filetransfer, tmp_path):
        """本地 poster 优先；历史展示由前端套用 display 变换，不在这里套消息模糊."""
        (tmp_path / "poster.jpg").write_bytes(b"x")

        class _Anchored:
            def as_dict(self):
                return {
                    "id": 1,
                    "mode": "link",
                    "dest_path": str(tmp_path),
                    "dest_filename": "movie.mkv",
                    "identity_id": "id-1",
                    "content_profile": "custom",
                }

        mock_filetransfer.get_transfer_history.return_value = (1, [_Anchored()])
        service._cache.clear()
        result = service.get_transfer_history_page("", 1, 20)

        image = result.result[0]["image"]
        assert image.startswith("/img/poster?path=")
        assert result.result[0]["CONTENT_PROFILE"] == "custom"

    def test_history_image_local_poster_without_anchor(self, service, mock_filetransfer, tmp_path):
        """旧记录没有锚点/TMDB 时仍优先使用目录内 poster.jpg."""
        (tmp_path / "poster.jpg").write_bytes(b"x")

        class _Legacy:
            def as_dict(self):
                return {
                    "id": 3,
                    "mode": "link",
                    "dest_path": str(tmp_path),
                    "dest_filename": "movie.mkv",
                }

        mock_filetransfer.get_transfer_history.return_value = (1, [_Legacy()])
        service._cache.clear()
        result = service.get_transfer_history_page("", 1, 20)

        assert result.result[0]["image"].startswith("/img/poster?path=")

    def test_history_image_uses_persisted_poster(self, service, mock_filetransfer):
        """转移时固化的 POSTER 直接使用，不再回查订阅/快照."""

        class _Persisted:
            def as_dict(self):
                return {
                    "id": 4,
                    "mode": "link",
                    "poster": "https://img.example/persisted.jpg",
                }

        mock_filetransfer.get_transfer_history.return_value = (1, [_Persisted()])
        service._cache.clear()
        result = service.get_transfer_history_page("", 1, 20)

        assert result.result[0]["image"] == "https://img.example/persisted.jpg"

    def test_history_image_falls_back_to_subscription(self, mock_filetransfer, mock_sync_service):
        """无本地 poster 时复用订阅海报，并回填内容画像."""
        subscribe_repo = MagicMock()
        subscribe_repo.get_movie_subscription_hint.return_value = {
            "image": "https://img.example/poster.jpg",
            "content_profile": "adult",
        }
        metadata_service = MagicMock()
        service = TransferHistoryService(
            filetransfer=mock_filetransfer,
            sync_service=mock_sync_service,
            cache_ttl=30,
            metadata_service=metadata_service,
            subscribe_repo=subscribe_repo,
        )

        class _Anchored:
            def as_dict(self):
                return {
                    "id": 2,
                    "mode": "link",
                    "title": "ABC-123",
                    "identity_id": "",
                    "anchor_provider": "content_id",
                    "anchor_external_id": "ABC-123",
                    "content_profile": "",
                }

        mock_filetransfer.get_transfer_history.return_value = (1, [_Anchored()])
        service._cache.clear()
        result = service.get_transfer_history_page("", 1, 20)

        rows = result.result or []
        assert rows[0]["image"] == "https://img.example/poster.jpg"
        assert rows[0]["CONTENT_PROFILE"] == "adult"
        subscribe_repo.get_movie_subscription_hint.assert_called_once_with(
            "content_id", "ABC-123", "ABC-123", identity_id=""
        )
        metadata_service.latest_snapshot_for_media.assert_not_called()

    def test_get_transfer_statistics(self, service, mock_filetransfer):
        mock_filetransfer.get_transfer_statistics.return_value = [
            ("movie", "2024-01-01", 5),
            ("tv", "2024-01-01", 3),
            ("anime", "2024-01-02", 2),
        ]
        mock_filetransfer.get_transfer_series_statistics.return_value = [
            ("2024-01-01", 2),
        ]
        result = service.get_transfer_statistics(days=7)
        assert result["labels"] == ["2024-01-01", "2024-01-02"]
        assert result["movie_nums"] == [5, 0]
        assert result["tv_nums"] == [3, 0]
        assert result["anime_nums"] == [0, 2]
        assert result["tv_series_nums"] == [2, 0]

    def test_get_transfer_statistics_skips_empty(self, service, mock_filetransfer):
        mock_filetransfer.get_transfer_statistics.return_value = [
            ("movie", "2024-01-01", 0),
            ("unknown", "2024-01-01", 1),
        ]
        mock_filetransfer.get_transfer_series_statistics.return_value = []
        result = service.get_transfer_statistics()
        assert result["labels"] == []
        assert result["movie_nums"] == []
        assert result["tv_nums"] == []
        assert result["anime_nums"] == []
        assert result["tv_series_nums"] == []

    def test_get_transfer_statistics_series_none(self, service, mock_filetransfer):
        mock_filetransfer.get_transfer_statistics.return_value = [
            ("tv", "2024-01-01", 4),
        ]
        mock_filetransfer.get_transfer_series_statistics.return_value = None
        result = service.get_transfer_statistics(days=7)
        assert result["tv_series_nums"] == [0]

    def test_get_unknown_list(self, service, mock_filetransfer):
        mock_filetransfer.get_transfer_unknown_paths.return_value = [_UnknownMock()]
        mock_filetransfer.get_sync_backend_by_dest.return_value = "smb"
        result = service.get_unknown_list()
        assert len(result) == 1
        assert result[0]["path"] == "C:/unknown/file.mkv"
        assert result[0]["to"] == "C:/dst"
        assert result[0]["dst_backend"] == "smb"

    def test_get_unknown_list_skips_empty_path(self, service, mock_filetransfer):
        empty = _UnknownMock()
        empty.PATH = None
        mock_filetransfer.get_transfer_unknown_paths.return_value = [empty]
        result = service.get_unknown_list()
        assert result == []

    def test_get_unknown_list_by_page(self, service, mock_filetransfer):
        mock_filetransfer.get_transfer_unknown_paths_by_page.return_value = (1, [_UnknownMock()])
        mock_filetransfer.get_sync_backend_by_dest.return_value = "local"
        result = service.get_unknown_list_by_page("", 1, 10)
        assert result.total == 1
        assert result.items[0]["path"] == "C:/unknown/file.mkv"

    def test_re_identify_unknown(self, service, mock_filetransfer, mock_sync_service):
        rec = _UnknownMock()
        rec.PATH = "/some/path.mkv"
        mock_filetransfer.get_transfer_unknown_paths.return_value = [rec]
        count = service.re_identify_unknown()
        assert count == 1
        mock_sync_service.re_identify_items.assert_called_once_with(flag="unidentification", ids=[10])

    def test_re_identify_unknown_empty(self, service, mock_filetransfer, mock_sync_service):
        mock_filetransfer.get_transfer_unknown_paths.return_value = []
        count = service.re_identify_unknown()
        assert count == 0
        mock_sync_service.re_identify_items.assert_not_called()

    def test_clear_history(self, service, mock_filetransfer):
        service.clear_history()
        mock_filetransfer.delete_transfer.assert_called_once()
        mock_filetransfer.truncate_transfer_blacklist.assert_called_once()


class TestTransferHistoryServiceCache:
    def test_get_transfer_history_page_uses_cache(self, service, mock_filetransfer):
        mock_filetransfer.get_transfer_history.return_value = (65, [_HistoryMock()])
        first = service.get_transfer_history_page("", 2, 20)
        second = service.get_transfer_history_page("", 2, 20)
        assert first == second
        mock_filetransfer.get_transfer_history.assert_called_once()

    def test_get_transfer_statistics_uses_cache(self, service, mock_filetransfer):
        mock_filetransfer.get_transfer_statistics.return_value = [("movie", "2024-01-01", 5)]
        first = service.get_transfer_statistics(days=7)
        second = service.get_transfer_statistics(days=7)
        assert first == second
        mock_filetransfer.get_transfer_statistics.assert_called_once()

    def test_get_unknown_list_uses_cache(self, service, mock_filetransfer):
        mock_filetransfer.get_transfer_unknown_paths.return_value = [_UnknownMock()]
        mock_filetransfer.get_sync_backend_by_dest.return_value = "local"
        first = service.get_unknown_list()
        second = service.get_unknown_list()
        assert first == second
        # 每次刷新都要检查文件存在性，因此会重复读取一次记录。
        mock_filetransfer.get_transfer_unknown_paths.assert_has_calls([call(), call()])

    def test_get_unknown_list_by_page_uses_cache(self, service, mock_filetransfer):
        mock_filetransfer.get_transfer_unknown_paths_by_page.return_value = (1, [_UnknownMock()])
        mock_filetransfer.get_sync_backend_by_dest.return_value = "local"
        first = service.get_unknown_list_by_page("", 1, 10)
        second = service.get_unknown_list_by_page("", 1, 10)
        assert first == second
        mock_filetransfer.get_transfer_unknown_paths_by_page.assert_called_once()

    def test_clear_history_clears_cache(self, service, mock_filetransfer):
        mock_filetransfer.get_transfer_unknown_paths.return_value = [_UnknownMock()]
        mock_filetransfer.get_sync_backend_by_dest.return_value = "local"
        service.get_unknown_list()
        service.clear_history()
        mock_filetransfer.get_transfer_unknown_paths.return_value = []
        result = service.get_unknown_list()
        assert result == []
        assert mock_filetransfer.get_transfer_unknown_paths.call_count == 4

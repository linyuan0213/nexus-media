"""媒体目录列表接口健壮性测试（统一走存储后端，异常返回空列表而非 500）."""

from unittest.mock import MagicMock

from app.services.media_file_service import MediaFileService
from app.storage.backends.base import FileInfo


def _service() -> MediaFileService:
    return MediaFileService(MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock())


def _service_with_backend(monkeypatch, backend) -> MediaFileService:
    svc = _service()
    monkeypatch.setattr(svc, "_resolve_backend", lambda _backend_id: backend)
    return svc


class TestGetDirList:
    def test_missing_path_returns_empty(self, monkeypatch):
        backend = MagicMock()
        backend.stat.return_value = None
        backend.list_dir.side_effect = FileNotFoundError("no such dir")
        assert _service_with_backend(monkeypatch, backend).get_dir_list("/Media/media") == []

    def test_permission_error_returns_empty(self, monkeypatch):
        backend = MagicMock()
        backend.stat.return_value = None
        backend.list_dir.side_effect = PermissionError("denied")
        assert _service_with_backend(monkeypatch, backend).get_dir_list("/Media/media") == []

    def test_local_missing_path_returns_empty(self):
        assert _service().get_dir_list("/definitely/not/exist/dir") == []

    def test_local_root_lists_without_error(self):
        assert isinstance(_service().get_dir_list("/"), list)

    def test_maps_file_info_fields(self, monkeypatch):
        backend = MagicMock()
        backend.stat.return_value = FileInfo(path="/m", size=0, mtime=1.0, is_dir=True)
        backend.list_dir.return_value = [FileInfo(path="/m/a.mkv", size=10, mtime=2.0, ctime=3.0, is_dir=False)]
        out = _service_with_backend(monkeypatch, backend).get_dir_list("/m")
        assert out[0]["name"] == "a.mkv"
        assert out[0]["ext"] == "mkv"
        assert out[0]["size"] == 10
        assert out[0]["ctime"] == 3.0
        assert out[0]["is_dir"] is False

    def test_file_path_lists_parent_dir(self, monkeypatch):
        backend = MagicMock()
        backend.stat.return_value = FileInfo(path="/m/a.mkv", size=1, mtime=1.0, is_dir=False)
        backend.list_dir.return_value = []
        _service_with_backend(monkeypatch, backend).get_dir_list("/m/a.mkv")
        backend.list_dir.assert_called_once_with("/m")

"""未识别列表文件存在性清理测试."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.transfer_history_service import TransferHistoryService


def test_prune_removes_missing_unknown_files(monkeypatch):
    service = TransferHistoryService.__new__(TransferHistoryService)
    service._filetransfer = MagicMock()
    service._cache = MagicMock()
    service._filetransfer.get_transfer_unknown_paths.return_value = [
        SimpleNamespace(ID=1, PATH="/exists/file.mkv"),
        SimpleNamespace(ID=2, PATH="/missing/file.mkv"),
    ]
    monkeypatch.setattr("app.services.transfer_history_service.os.path.exists", lambda path: path.startswith("/exists"))

    service._prune_missing_unknown()

    service._filetransfer.delete_transfer_unknowns.assert_called_once_with([2])
    service._cache.clear.assert_called_once()


def test_prune_keeps_existing_unknown_files(monkeypatch):
    service = TransferHistoryService.__new__(TransferHistoryService)
    service._filetransfer = MagicMock()
    service._cache = MagicMock()
    service._filetransfer.get_transfer_unknown_paths.return_value = [
        SimpleNamespace(ID=1, PATH="/exists/file.mkv"),
    ]
    monkeypatch.setattr("app.services.transfer_history_service.os.path.exists", lambda path: True)

    service._prune_missing_unknown()

    service._filetransfer.delete_transfer_unknowns.assert_not_called()

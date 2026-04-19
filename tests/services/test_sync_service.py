# -*- coding: utf-8 -*-
"""
SyncService 单元测试
"""
from unittest.mock import MagicMock, patch

import pytest

from app.schemas.sync import ManualTransferResultDTO, ReIdentifyResultDTO
from app.services.sync_service import SyncService
from app.utils.types import MediaType


class FakeTransferInfo:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.fixture
def mock_sync():
    return MagicMock()


@pytest.fixture
def mock_filetransfer():
    return MagicMock()


@pytest.fixture
def mock_media():
    return MagicMock()


@pytest.fixture
def svc(mock_sync, mock_filetransfer, mock_media):
    return SyncService(sync=mock_sync, filetransfer=mock_filetransfer, media=mock_media)


class TestValidateSyncPath:
    def test_empty_source(self, svc):
        ok, msg = svc.validate_sync_path("", "/dest", "link")
        assert ok is False
        assert "源目录不能为空" in msg

    @patch('os.path.exists')
    def test_source_not_exists(self, mock_exists, svc):
        mock_exists.return_value = False
        ok, msg = svc.validate_sync_path("/src", "/dest", "link")
        assert ok is False
        assert "目录不存在" in msg

    @patch('os.path.exists')
    def test_link_cross_disk(self, mock_exists, svc):
        mock_exists.return_value = True
        ok, msg = svc.validate_sync_path("/src", "/dest", "link")
        assert ok is False
        assert "硬链接不能跨盘" in msg

    @patch('os.path.exists')
    def test_valid(self, mock_exists, svc):
        mock_exists.return_value = True
        ok, msg = svc.validate_sync_path("/src", "/dest", "copy")
        assert ok is True


class TestAddOrEditSyncPath:
    @patch('os.path.exists')
    def test_add_new(self, mock_exists, svc, mock_sync):
        mock_exists.return_value = True
        ok, msg = svc.add_or_edit_sync_path(
            sid=None, source="/src", dest="/dest",
            unknown="/unknown", mode="copy",
            compatibility=1, rename=1, enabled=1
        )
        assert ok is True
        mock_sync.check_source.assert_called_once()
        mock_sync.insert_sync_path.assert_called_once()

    @patch('os.path.exists')
    def test_edit_existing(self, mock_exists, svc, mock_sync):
        mock_exists.return_value = True
        ok, msg = svc.add_or_edit_sync_path(
            sid=5, source="/src", dest="/dest",
            unknown="", mode="copy",
            compatibility=0, rename=0, enabled=0
        )
        assert ok is True
        mock_sync.delete_sync_path.assert_called_once_with(5)


class TestCheckSyncPath:
    def test_compatibility(self, svc, mock_sync):
        ok, msg = svc.check_sync_path(1, "compatibility", True)
        assert ok is True
        mock_sync.check_sync_paths.assert_called_once_with(sid=1, compatibility=1)

    def test_enable(self, svc, mock_sync):
        ok, msg = svc.check_sync_path(1, "enable", True)
        assert ok is True
        mock_sync.check_source.assert_called_once_with(sid=1)

    def test_invalid_flag(self, svc):
        ok, msg = svc.check_sync_path(1, "invalid", True)
        assert ok is False


class TestBuildMediaType:
    def test_movie(self):
        assert SyncService.build_media_type("MOV") == MediaType.MOVIE

    def test_tv(self):
        assert SyncService.build_media_type("TV") == MediaType.TV

    def test_anime(self):
        assert SyncService.build_media_type("ANIME") == MediaType.ANIME


class TestManualTransfer:
    @patch('os.path.exists')
    def test_path_not_exists(self, mock_exists, svc):
        mock_exists.return_value = False
        result = svc.manual_transfer("/in", None)
        assert result.success is False
        assert "输入路径不存在" in result.message

    @patch('os.path.exists')
    def test_with_tmdb(self, mock_exists, svc, mock_media, mock_filetransfer):
        mock_exists.return_value = True
        mock_media.get_tmdb_info.return_value = {"id": 123}
        mock_filetransfer.transfer_media.return_value = (True, "")
        result = svc.manual_transfer(
            "/in", "copy", "/out", MediaType.MOVIE,
            tmdbid=123
        )
        assert result.success is True

    @patch('os.path.exists')
    def test_without_tmdb(self, mock_exists, svc, mock_filetransfer):
        mock_exists.return_value = True
        mock_filetransfer.transfer_media.return_value = (True, "")
        result = svc.manual_transfer("/in", "copy", "/out", MediaType.TV)
        assert result.success is True

    @patch('os.path.exists')
    def test_tmdb_not_found(self, mock_exists, svc, mock_media):
        mock_exists.return_value = True
        mock_media.get_tmdb_info.return_value = None
        result = svc.manual_transfer("/in", "copy", "/out", MediaType.MOVIE, tmdbid=123)
        assert result.success is False
        assert "无法查询到TMDB信息" in result.message


class TestReIdentifyItems:
    def test_unidentification_success(self, svc, mock_filetransfer):
        mock_filetransfer.get_unknown_info_by_id.return_value = FakeTransferInfo(
            PATH="/path", DEST="/dest", MODE="link"
        )
        mock_filetransfer.transfer_media.return_value = (True, "")
        result = svc.re_identify_items("unidentification", [1])
        assert result.success is True
        mock_filetransfer.update_transfer_unknown_state.assert_called_once()

    def test_unidentification_not_found(self, svc, mock_filetransfer):
        mock_filetransfer.get_unknown_info_by_id.return_value = None
        result = svc.re_identify_items("unidentification", [1])
        assert result.success is False
        assert "未查询到未识别记录" in result.message

    def test_history_success(self, svc, mock_filetransfer):
        mock_filetransfer.get_transfer_info_by_id.return_value = FakeTransferInfo(
            SOURCE_PATH="/src", SOURCE_FILENAME="file.mkv", DEST="/dest", MODE="copy"
        )
        mock_filetransfer.transfer_media.return_value = (True, "")
        result = svc.re_identify_items("history", [1])
        assert result.success is True

    def test_history_not_found(self, svc, mock_filetransfer):
        mock_filetransfer.get_transfer_info_by_id.return_value = None
        result = svc.re_identify_items("history", [1])
        assert result.success is False
        assert "未查询到转移日志记录" in result.message

    def test_mixed_results(self, svc, mock_filetransfer):
        mock_filetransfer.get_unknown_info_by_id.side_effect = [
            FakeTransferInfo(PATH="/p1", DEST="/d1", MODE="link"),
            FakeTransferInfo(PATH="/p2", DEST="/d2", MODE="copy"),
        ]
        mock_filetransfer.transfer_media.side_effect = [
            (True, ""), (False, "错误1")
        ]
        result = svc.re_identify_items("unidentification", [1, 2])
        assert result.success is False
        assert "错误1" in result.message

    def test_invalid_flag(self, svc):
        result = svc.re_identify_items("invalid", [1])
        assert result.success is False
        assert "不支持的识别类型" in result.message


class TestGetSyncPaths:
    def test_get_all(self, svc, mock_sync):
        mock_sync.get_sync_path_conf.return_value = {"1": {"from": "/src"}}
        result = svc.get_sync_paths()
        assert result == {"1": {"from": "/src"}}

    def test_get_by_id(self, svc, mock_sync):
        mock_sync.get_sync_path_conf.return_value = {"from": "/src"}
        result = svc.get_sync_paths(sid=1)
        assert result == {"from": "/src"}

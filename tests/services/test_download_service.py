# -*- coding: utf-8 -*-
"""
DownloadService 单元测试
"""
from unittest.mock import MagicMock, patch

import pytest

from app.schemas.download import (
    DownloadResultDTO,
    IndexerStatisticsDTO,
)
from app.services.download_service import DownloadService


class FakeSearchResult:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class FakeDownloadInfo:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.fixture
def mock_downloader():
    return MagicMock()


@pytest.fixture
def mock_searcher():
    return MagicMock()


@pytest.fixture
def mock_media():
    return MagicMock()


@pytest.fixture
def mock_sites():
    return MagicMock()


@pytest.fixture
def mock_indexer_service():
    return MagicMock()


@pytest.fixture
def mock_remover():
    return MagicMock()


@pytest.fixture
def svc(mock_downloader, mock_searcher, mock_media, mock_sites, mock_indexer_service, mock_remover):
    return DownloadService(
        downloader=mock_downloader,
        searcher=mock_searcher,
        media=mock_media,
        sites=mock_sites,
        indexer_service=mock_indexer_service,
        torrent_remover=mock_remover
    )


class TestResolveDownloadUrl:
    def test_mteam_none_enclosure(self, svc, mock_downloader):
        mock_downloader.get_download_url.return_value = "http://dl.url"
        assert svc._resolve_download_url("https://m-team.cc", None) == "http://dl.url"

    def test_normal_url_with_enclosure(self, svc):
        assert svc._resolve_download_url("https://example.com", "enc123") == "enc123"

    def test_normal_url_without_enclosure(self, svc):
        assert svc._resolve_download_url("https://example.com", None) == ""


class TestDownloadFromSearchResults:
    def test_empty_results(self, svc, mock_searcher):
        mock_searcher.get_search_result_by_id.return_value = []
        result = svc.download_from_search_results(1, "/dl", "s1", "user")
        assert result.success is False
        assert "未找到" in result.message

    def test_success(self, svc, mock_searcher, mock_media, mock_downloader):
        mock_searcher.get_search_result_by_id.return_value = [
            FakeSearchResult(
                PAGEURL="https://example.com", ENCLOSURE="enc1",
                TORRENT_NAME="Test", DESCRIPTION="", SIZE=100,
                SITE="Site", UPLOAD_VOLUME_FACTOR=1.0, DOWNLOAD_VOLUME_FACTOR=1.0
            )
        ]
        mock_media.get_media_info.return_value = MagicMock()
        mock_downloader.download.return_value = (None, True, "")
        result = svc.download_from_search_results(1, "/dl", "s1", "user")
        assert result.success is True

    def test_mteam_special_url(self, svc, mock_searcher, mock_media, mock_downloader):
        mock_searcher.get_search_result_by_id.return_value = [
            FakeSearchResult(
                PAGEURL="https://m-team.cc", ENCLOSURE=None,
                TORRENT_NAME="Test", DESCRIPTION="", SIZE=100,
                SITE="Site", UPLOAD_VOLUME_FACTOR=1.0, DOWNLOAD_VOLUME_FACTOR=1.0
            )
        ]
        mock_downloader.get_download_url.return_value = "http://special"
        mock_media.get_media_info.return_value = MagicMock()
        mock_downloader.download.return_value = (None, True, "")
        result = svc.download_from_search_results(1, "/dl", "s1", "user")
        assert result.success is True
        mock_downloader.get_download_url.assert_called_once()

    def test_download_fail(self, svc, mock_searcher, mock_media, mock_downloader):
        mock_searcher.get_search_result_by_id.return_value = [
            FakeSearchResult(
                PAGEURL="https://example.com", ENCLOSURE="enc1",
                TORRENT_NAME="Test", DESCRIPTION="", SIZE=100,
                SITE="Site", UPLOAD_VOLUME_FACTOR=1.0, DOWNLOAD_VOLUME_FACTOR=1.0
            )
        ]
        mock_media.get_media_info.return_value = MagicMock()
        mock_downloader.download.return_value = (None, False, "磁盘已满")
        result = svc.download_from_search_results(1, "/dl", "s1", "user")
        assert result.success is False
        assert "磁盘已满" in result.message


class TestDownloadFromLink:
    def test_missing_info(self, svc):
        result = svc.download_from_link(
            "", "", "", "", "", "", "", "", "", "/dl", "s1", "user"
        )
        assert result.success is False
        assert "种子信息有误" in result.message

    def test_success(self, svc, mock_media, mock_downloader):
        mock_media.get_media_info.return_value = MagicMock()
        mock_downloader.download.return_value = (None, True, "")
        result = svc.download_from_link(
            "site", "enc", "title", "desc", "page", "100", "10",
            "1.0", "1.0", "/dl", "s1", "user"
        )
        assert result.success is True
        assert result.message == "下载成功"

    def test_mteam_special(self, svc, mock_media, mock_downloader):
        mock_downloader.get_download_url.return_value = "http://special"
        mock_media.get_media_info.return_value = MagicMock()
        mock_downloader.download.return_value = (None, True, "")
        result = svc.download_from_link(
            "site", "", "title", "desc", "https://m-team.cc", "100", "10",
            "1.0", "1.0", "/dl", "s1", "user"
        )
        assert result.success is True

    def test_media_none(self, svc, mock_media):
        mock_media.get_media_info.return_value = None
        result = svc.download_from_link(
            "site", "enc", "title", "desc", "page", "100", "10",
            "1.0", "1.0", "/dl", "s1", "user"
        )
        assert result.success is False
        assert "识别失败" in result.message


class TestDownloadFromTorrentFilesOrUrls:
    def test_empty_input(self, svc):
        result = svc.download_from_torrent_files_or_urls([], [], "/dl", "s1", "user")
        assert result.success is False
        assert "没有种子文件" in result.message

    def test_from_files_only(self, svc, mock_downloader, mock_media):
        with patch('app.services.download_service.temp_manager') as mock_temp:
            mock_temp.get_temp_path.return_value = "/tmp/test.torrent"
            mock_media.get_media_info.return_value = MagicMock()
            mock_downloader.download.return_value = (None, True, "")
            result = svc.download_from_torrent_files_or_urls(
                [{"upload": {"filename": "test.torrent"}}], [], "/dl", "s1", "user"
            )
            assert result.success is True

    def test_from_magnet_url(self, svc, mock_downloader):
        mock_downloader.download.return_value = (None, True, "")
        result = svc.download_from_torrent_files_or_urls(
            [], ["magnet:?xt=urn:btih:abc"], "/dl", "s1", "user"
        )
        assert result.success is True

    def test_from_url_torrent_fail(self, svc, mock_sites):
        mock_sites.get_sites.return_value = {"cookie": "c", "ua": "u", "proxy": False}
        with patch('app.services.download_service.Torrent') as MockTorrent:
            MockTorrent().get_torrent_info.return_value = (None, None, None, None, "超时")
            result = svc.download_from_torrent_files_or_urls(
                [], ["http://example.com/torrent"], "/dl", "s1", "user"
            )
            assert result.success is False
            assert "下载种子文件失败" in result.message


class TestGetDownloadingWithMediaInfo:
    def test_from_download_history(self, svc, mock_downloader):
        mock_downloader.get_downloading_progress.return_value = [
            {"id": "1", "name": "raw_name"}
        ]
        mock_downloader.default_downloader_id = "qb"
        mock_downloader.get_download_history_by_downloader.return_value = FakeDownloadInfo(
            TITLE="Movie", YEAR="2020", POSTER="/poster.jpg", SE="S01"
        )
        result = svc.get_downloading_with_media_info()
        assert result[0]["title"] == "Movie (2020) S01"
        assert result[0]["image"] == "/poster.jpg"

    def test_from_media_info(self, svc, mock_downloader, mock_media):
        mock_downloader.get_downloading_progress.return_value = [
            {"id": "1", "name": "raw_name"}
        ]
        mock_downloader.default_downloader_id = "qb"
        mock_downloader.get_download_history_by_downloader.return_value = None
        mock_media_info = MagicMock()
        mock_media_info.year = "2021"
        mock_media_info.title = "TV Show"
        mock_media_info.get_season_episode_string.return_value = "S02E03"
        mock_media_info.get_poster_image.return_value = "/tv.jpg"
        mock_media.get_media_info.return_value = mock_media_info
        result = svc.get_downloading_with_media_info()
        assert result[0]["title"] == "TV Show (2021) S02E03"
        assert result[0]["image"] == "/tv.jpg"

    def test_media_none(self, svc, mock_downloader, mock_media):
        mock_downloader.get_downloading_progress.return_value = [
            {"id": "1", "name": "raw_name"}
        ]
        mock_downloader.default_downloader_id = "qb"
        mock_downloader.get_download_history_by_downloader.return_value = None
        mock_media.get_media_info.return_value = None
        result = svc.get_downloading_with_media_info()
        assert result[0]["title"] == "raw_name"
        assert result[0]["image"] == ""

    def test_no_year(self, svc, mock_downloader, mock_media):
        mock_downloader.get_downloading_progress.return_value = [
            {"id": "1", "name": "raw_name"}
        ]
        mock_downloader.default_downloader_id = "qb"
        mock_downloader.get_download_history_by_downloader.return_value = None
        mock_media_info = MagicMock()
        mock_media_info.year = None
        mock_media_info.title = "Movie"
        mock_media_info.get_season_episode_string.return_value = ""
        mock_media_info.get_poster_image.return_value = ""
        mock_media.get_media_info.return_value = mock_media_info
        result = svc.get_downloading_with_media_info()
        assert result[0]["title"] == "Movie "


class TestGetIndexerStatistics:
    def test_empty(self, svc, mock_indexer_service):
        mock_indexer_service.get_indexer_statistics.return_value = ([], [["indexer", "avg"]])
        stats, dataset = svc.get_indexer_statistics()
        assert stats == []
        assert dataset == [["indexer", "avg"]]

    def test_with_data(self, svc, mock_indexer_service):
        from app.schemas.download import IndexerStatisticsDTO
        mock_indexer_service.get_indexer_statistics.return_value = (
            [IndexerStatisticsDTO(name="Indexer1", total=100, fail=10, success=90, avg=88.5)],
            [["indexer", "avg"], ["Indexer1", 88.5]]
        )
        stats, dataset = svc.get_indexer_statistics()
        assert len(stats) == 1
        assert stats[0].name == "Indexer1"
        assert stats[0].avg == 88.5
        assert dataset == [["indexer", "avg"], ["Indexer1", 88.5]]


class TestTorrentRemoverDelegates:
    def test_auto_remove(self, svc, mock_remover):
        svc.auto_remove_torrents(taskids=[1, 2])
        mock_remover.auto_remove_torrents.assert_called_once_with(taskids=[1, 2])

    def test_get_remove_torrents(self, svc, mock_remover):
        mock_remover.get_remove_torrents.return_value = (True, [{"id": "1"}])
        flag, torrents = svc.get_remove_torrents(taskid=1)
        assert flag is True
        assert len(torrents) == 1

    def test_get_tasks(self, svc, mock_remover):
        mock_remover.get_torrent_remove_tasks.return_value = [{"id": 1}]
        result = svc.get_torrent_remove_tasks(taskid=1)
        assert result == [{"id": 1}]

    def test_update_task(self, svc, mock_remover):
        mock_remover.update_torrent_remove_task.return_value = (True, "")
        flag, msg = svc.update_torrent_remove_task(data={"name": "test"})
        assert flag is True

    def test_delete_task(self, svc, mock_remover):
        mock_remover.delete_torrent_remove_task.return_value = True
        assert svc.delete_torrent_remove_task(taskid=1) is True

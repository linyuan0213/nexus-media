"""Tests for app.services.rss._articles module."""

from unittest.mock import MagicMock, patch


from app.services.rss._articles import (
    _check_rss_articles,
    _download_rss_articles,
    _get_rss_articles,
    _test_rss_articles,
)


class TestGetRssArticles:
    """Test suite for _get_rss_articles function."""

    def test_none_taskid_returns_none(self):
        """None taskid should return None."""
        service = MagicMock()
        result = _get_rss_articles(service, None)
        assert result is None

    @patch("app.services.rss._articles._parse_userrss_result")
    def test_empty_rss_result_returns_empty_list(self, mock_parse):
        """Empty RSS result should return empty list."""
        service = MagicMock()
        service.get_rsstask_info.return_value = {"uses": "D"}
        mock_parse.return_value = []

        result = _get_rss_articles(service, 1)
        assert result == []
        service.get_rsstask_info.assert_called_once_with(1)

    @patch("app.services.rss._articles._parse_userrss_result")
    def test_successful_article_extraction(self, mock_parse):
        """Successfully extract articles from RSS result."""
        service = MagicMock()
        service.get_rsstask_info.return_value = {"uses": "D"}
        service.is_article_processed.return_value = False
        mock_parse.return_value = [
            {
                "title": "Test Movie",
                "enclosure": "http://test.torrent",
                "link": "http://test.page",
                "size": 1024,
                "date": "2024-01-01",
                "year": "2024",
            }
        ]

        result = _get_rss_articles(service, 1)

        assert len(result) == 1
        assert result[0]["title"] == "Test Movie"
        assert result[0]["finish_flag"] is False


class TestCheckRssArticles:
    """Test suite for _check_rss_articles function."""

    def test_invalid_flag_returns_false(self):
        """Invalid flag should return False."""
        service = MagicMock()
        service.get_rsstask_info.return_value = {"uses": "D"}
        result = _check_rss_articles(service, 1, "invalid_flag", [])
        assert result is False

    def test_set_finished_download_type(self):
        """set_finished with download type should insert torrents."""
        service = MagicMock()
        service.get_rsstask_info.return_value = {"uses": "D"}
        service.is_article_processed.return_value = False

        articles = [{"title": "Test", "enclosure": "http://test", "year": "2024"}]
        result = _check_rss_articles(service, 1, "set_finished", articles)

        assert result is True
        service.rsshelper.simple_insert_rss_torrents.assert_called_once_with("Test 2024", "http://test")

    def test_set_unfinish_download_type(self):
        """set_unfinish with download type should delete torrents."""
        service = MagicMock()
        service.get_rsstask_info.return_value = {"uses": "D"}

        articles = [{"title": "Test", "enclosure": "http://test", "year": "2024"}]
        result = _check_rss_articles(service, 1, "set_unfinish", articles)

        assert result is True
        service.rsshelper.simple_delete_rss_torrents.assert_called_once_with("Test 2024", "http://test")

    def test_already_processed_skips(self):
        """Already processed articles should be skipped."""
        service = MagicMock()
        service.get_rsstask_info.return_value = {"uses": "D"}
        service.is_article_processed.return_value = True

        articles = [{"title": "Test", "enclosure": "http://test", "year": "2024"}]
        result = _check_rss_articles(service, 1, "set_finished", articles)

        assert result is True
        service.rsshelper.simple_insert_rss_torrents.assert_not_called()


class TestDownloadRssArticles:
    """Test suite for _download_rss_articles function."""

    def test_none_taskid_returns_none(self):
        """None taskid should return None."""
        service = MagicMock()
        result = _download_rss_articles(service, None, [])
        assert result is None

    def test_download_failure_returns_false(self):
        """Download failure should return False."""
        service = MagicMock()
        service.get_rsstask_info.return_value = {"save_path": "/test", "download_setting": "", "proxy": False}
        service.media.get_media_info.return_value = MagicMock()
        service.downloader.download.return_value = (1, False, "error")

        articles = [{"title": "Test", "enclosure": "http://test"}]
        result = _download_rss_articles(service, 1, articles)

        assert result is False

    def test_download_success(self):
        """Successful download should insert records."""
        service = MagicMock()
        service.get_rsstask_info.return_value = {"save_path": "/test", "download_setting": "", "proxy": False}
        service.media.get_media_info.return_value = MagicMock()
        service.downloader.download.return_value = (1, True, "")
        service.downloader.get_downloader_conf.return_value = {"name": "qBittorrent"}

        articles = [{"title": "Test", "enclosure": "http://test"}]
        result = _download_rss_articles(service, 1, articles)

        assert result is True
        service.config_repo.insert_userrss_task_history.assert_called_once()


class TestTestRssArticles:
    """Test suite for _test_rss_articles function."""

    def test_none_taskid_returns_none(self):
        """None taskid should return None."""
        service = MagicMock()
        service.get_rsstask_info.return_value = None
        result = _test_rss_articles(service, None, "Test")
        assert result is None

    def test_media_info_failure_returns_none(self):
        """Media info failure should return None."""
        service = MagicMock()
        service.get_rsstask_info.return_value = {"uses": "D"}
        service.media.get_media_info.return_value = None

        result = _test_rss_articles(service, 1, "Test")
        assert result is None

    def test_successful_test(self):
        """Successful test should return media_info and flags."""
        media_mock = MagicMock()
        media_mock.type = MagicMock()
        media_mock.tmdb_id = 123

        service = MagicMock()
        service.get_rsstask_info.return_value = {"uses": "D", "filter": 1}
        service.media.get_media_info.return_value = media_mock
        service.filter.check_torrent_filter.return_value = (True, 1, "匹配成功")
        service.downloader.check_exists_medias.return_value = (False, {}, None)

        result = _test_rss_articles(service, 1, "Test")

        assert result is not None
        assert result[1] is True  # match_flag
        assert result[2] is False  # exist_flag

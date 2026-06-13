"""Tests for app.services.rss_automation.task_service module."""

from unittest.mock import MagicMock, patch

from app.services.rss_automation.task_service import RssTaskService


def _make_service(**kwargs):
    """Helper to create RssTaskService with mocked DI dependencies."""
    defaults = {
        "config_repo": MagicMock(),
        "rss_repo": MagicMock(),
        "rsshelper": MagicMock(),
        "message": MagicMock(),
        "searcher": MagicMock(),
        "filter_": MagicMock(),
        "media": MagicMock(),
        "downloader": MagicMock(),
        "scheduler_core": MagicMock(),
        "site_engine": MagicMock(),
    }
    defaults.update(kwargs)
    return RssTaskService(**defaults)


class TestRssTaskService:
    """Test suite for RssTaskService class."""

    def test_init_default_dependencies(self):
        """Default initialization should create all dependencies."""
        with patch("app.services.rss_automation.task_service.UserRssConfigRepositoryAdapter") as mock_repo:
            mock_repo_instance = MagicMock()
            mock_repo.return_value = mock_repo_instance
            service = RssTaskService(
                config_repo=mock_repo_instance,
                rss_repo=MagicMock(),
                rsshelper=MagicMock(),
                message=MagicMock(),
                searcher=MagicMock(),
                filter_=MagicMock(),
                media=MagicMock(),
                downloader=MagicMock(),
                scheduler_core=MagicMock(),
                site_engine=MagicMock(),
            )
            assert service.config_repo is mock_repo_instance

    def test_get_rsstask_info_no_taskid(self):
        """get_rsstask_info with no taskid should return all tasks."""
        service = _make_service()
        service._rss_tasks = [{"id": 1, "name": "test"}]
        result = service.get_rsstask_info()
        assert result == [{"id": 1, "name": "test"}]

    def test_get_rsstask_info_with_taskid(self):
        """get_rsstask_info with taskid should return specific task."""
        service = _make_service()
        service._rss_tasks = [{"id": 1, "name": "test"}, {"id": 2, "name": "test2"}]
        result = service.get_rsstask_info(2)
        assert result == {"id": 2, "name": "test2"}

    def test_get_rsstask_info_not_found(self):
        """get_rsstask_info with non-existent taskid should fall through to all tasks."""
        service = _make_service()
        service._rss_tasks = [{"id": 1, "name": "test"}]
        result = service.get_rsstask_info(999)
        assert result == [{"id": 1, "name": "test"}]

    def test_get_userrss_parser_no_pid(self):
        """get_userrss_parser with no pid should return all parsers."""
        service = _make_service()
        service._rss_parsers = [{"id": 1, "name": "parser1"}]
        result = service.get_userrss_parser()
        assert result == [{"id": 1, "name": "parser1"}]

    def test_get_userrss_parser_with_pid(self):
        """get_userrss_parser with pid should return specific parser."""
        service = _make_service()
        service._rss_parsers = [{"id": 1, "name": "parser1"}, {"id": 2, "name": "parser2"}]
        result = service.get_userrss_parser(2)
        assert result == {"id": 2, "name": "parser2"}

    def test_get_userrss_parser_not_found(self):
        """get_userrss_parser with non-existent pid should return empty dict."""
        service = _make_service()
        service._rss_parsers = [{"id": 1, "name": "parser1"}]
        result = service.get_userrss_parser(999)
        assert result == {}

    def test_is_article_processed_download_type(self):
        """is_article_processed for download type should check rsshelper."""
        service = _make_service()
        service.rsshelper = MagicMock()
        service.rsshelper.is_rssd_by_simple.return_value = True
        result = service.is_article_processed("D", "Test", "2024", "http://test")
        assert result is True
        service.rsshelper.is_rssd_by_simple.assert_called_once_with("Test 2024", "http://test")

    def test_is_article_processed_subscribe_type(self):
        """is_article_processed for subscribe type should check rsshelper with meta_name."""
        service = _make_service()
        service.rsshelper = MagicMock()
        service.rsshelper.is_rssd_by_simple.return_value = False
        result = service.is_article_processed("R", "Test", "2024", "http://test")
        assert result is False
        service.rsshelper.is_rssd_by_simple.assert_called_once_with("Test 2024", "Test 2024")

    def test_is_article_processed_unknown_type(self):
        """is_article_processed for unknown type should return False."""
        service = _make_service()
        result = service.is_article_processed("X", "Test", "2024", "http://test")
        assert result is False

    def test_crud_methods_call_config_repo(self):
        """CRUD methods should call config_repo and then _refresh."""
        service = _make_service()
        service.config_repo = MagicMock()
        service.config_repo.delete_userrss_task.return_value = True

        with patch.object(service, "_refresh") as mock_refresh:
            result = service.delete_userrss_task(1)
            service.config_repo.delete_userrss_task.assert_called_once_with(1)
            mock_refresh.assert_called_once()
            assert result is True

    def test_get_userrss_task_history(self):
        """get_userrss_task_history should delegate to config_repo."""
        service = _make_service()
        service.config_repo = MagicMock()
        service.config_repo.get_userrss_task_history.return_value = [{"id": 1}]
        result = service.get_userrss_task_history(1)
        service.config_repo.get_userrss_task_history.assert_called_once_with(1)
        assert result == [{"id": 1}]

    def test_stop_service(self):
        """stop_service should remove all jobs from scheduler."""
        mock_scheduler = MagicMock()
        service = _make_service(scheduler_core=mock_scheduler)
        service.stop_service()
        mock_scheduler.remove_all_jobs.assert_called_once_with(jobstore="rsscheck")

    def test_init_config_reads_parsers(self):
        """init_config should read parsers from config_repo."""
        parser_mock = MagicMock()
        parser_mock.ID = 1
        parser_mock.NAME = "TestParser"
        parser_mock.TYPE = "XML"
        parser_mock.FORMAT = "{}"
        parser_mock.PARAMS = None
        parser_mock.NOTE = None

        config_repo = MagicMock()
        config_repo.get_userrss_parser.return_value = [parser_mock]
        config_repo.get_userrss_tasks.return_value = []

        service = _make_service(config_repo=config_repo)
        with patch.object(service, "stop_service"):
            service._refresh()

        assert len(service._rss_parsers) == 1
        assert service._rss_parsers[0]["id"] == 1
        assert service._rss_parsers[0]["name"] == "TestParser"

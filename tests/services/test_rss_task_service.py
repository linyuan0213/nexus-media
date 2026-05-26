"""Tests for app.services.rss.task_service module."""

from unittest.mock import MagicMock, patch


from app.services.rss.task_service import RssTaskService


class TestRssTaskService:
    """Test suite for RssTaskService class."""

    def test_init_default_dependencies(self):
        """Default initialization should create all dependencies."""
        with (
            patch("app.services.rss.task_service.UserRssConfigRepositoryAdapter") as mock_repo,
            patch("app.services.rss.task_service.RssHistoryRepositoryAdapter"),
            patch("app.services.rss.task_service.RssHelper"),
            patch("app.services.rss.task_service.Message"),
            patch("app.services.rss.task_service.Searcher"),
            patch("app.services.rss.task_service.Filter"),
            patch("app.services.rss.task_service.MediaService"),
            patch("app.services.rss.task_service.Downloader"),
            patch("app.services.rss.task_service.Subscribe"),
        ):
            mock_repo_instance = MagicMock()
            mock_repo.return_value = mock_repo_instance
            service = RssTaskService()
            assert service.config_repo is mock_repo_instance

    def test_get_rsstask_info_no_taskid(self):
        """get_rsstask_info with no taskid should return all tasks."""
        service = RssTaskService()
        service._rss_tasks = [{"id": 1, "name": "test"}]
        result = service.get_rsstask_info()
        assert result == [{"id": 1, "name": "test"}]

    def test_get_rsstask_info_with_taskid(self):
        """get_rsstask_info with taskid should return specific task."""
        service = RssTaskService()
        service._rss_tasks = [{"id": 1, "name": "test"}, {"id": 2, "name": "test2"}]
        result = service.get_rsstask_info(2)
        assert result == {"id": 2, "name": "test2"}

    def test_get_rsstask_info_not_found(self):
        """get_rsstask_info with non-existent taskid should fall through to all tasks."""
        service = RssTaskService()
        service._rss_tasks = [{"id": 1, "name": "test"}]
        result = service.get_rsstask_info(999)
        assert result == [{"id": 1, "name": "test"}]

    def test_get_userrss_parser_no_pid(self):
        """get_userrss_parser with no pid should return all parsers."""
        service = RssTaskService()
        service._rss_parsers = [{"id": 1, "name": "parser1"}]
        result = service.get_userrss_parser()
        assert result == [{"id": 1, "name": "parser1"}]

    def test_get_userrss_parser_with_pid(self):
        """get_userrss_parser with pid should return specific parser."""
        service = RssTaskService()
        service._rss_parsers = [{"id": 1, "name": "parser1"}, {"id": 2, "name": "parser2"}]
        result = service.get_userrss_parser(2)
        assert result == {"id": 2, "name": "parser2"}

    def test_get_userrss_parser_not_found(self):
        """get_userrss_parser with non-existent pid should return empty dict."""
        service = RssTaskService()
        service._rss_parsers = [{"id": 1, "name": "parser1"}]
        result = service.get_userrss_parser(999)
        assert result == {}

    def test_is_article_processed_download_type(self):
        """is_article_processed for download type should check rsshelper."""
        service = RssTaskService()
        service.rsshelper = MagicMock()
        service.rsshelper.is_rssd_by_simple.return_value = True
        result = service.is_article_processed("D", "Test", "2024", "http://test")
        assert result is True
        service.rsshelper.is_rssd_by_simple.assert_called_once_with("Test 2024", "http://test")

    def test_is_article_processed_subscribe_type(self):
        """is_article_processed for subscribe type should check rsshelper with meta_name."""
        service = RssTaskService()
        service.rsshelper = MagicMock()
        service.rsshelper.is_rssd_by_simple.return_value = False
        result = service.is_article_processed("R", "Test", "2024", "http://test")
        assert result is False
        service.rsshelper.is_rssd_by_simple.assert_called_once_with("Test 2024", "Test 2024")

    def test_is_article_processed_unknown_type(self):
        """is_article_processed for unknown type should return False."""
        service = RssTaskService()
        result = service.is_article_processed("X", "Test", "2024", "http://test")
        assert result is False

    def test_crud_methods_call_config_repo(self):
        """CRUD methods should call config_repo and then init_config."""
        service = RssTaskService()
        service.config_repo = MagicMock()
        service.config_repo.delete_userrss_task.return_value = True

        with patch.object(service, "init_config") as mock_init:
            result = service.delete_userrss_task(1)
            service.config_repo.delete_userrss_task.assert_called_once_with(1)
            mock_init.assert_called_once()
            assert result is True

    def test_get_userrss_task_history(self):
        """get_userrss_task_history should delegate to config_repo."""
        service = RssTaskService()
        service.config_repo = MagicMock()
        service.config_repo.get_userrss_task_history.return_value = [{"id": 1}]
        result = service.get_userrss_task_history(1)
        service.config_repo.get_userrss_task_history.assert_called_once_with(1)
        assert result == [{"id": 1}]

    def test_stop_service(self):
        """stop_service should remove all jobs from scheduler."""
        service = RssTaskService()
        with patch("app.services.rss.task_service.SchedulerCore") as mock_scheduler:
            service.stop_service()
            mock_scheduler.return_value.remove_all_jobs.assert_called_once_with(jobstore="rsscheck")

    def test_init_config_reads_parsers(self):
        """init_config should read parsers from config_repo."""
        from app.utils.commons import SingletonMeta

        SingletonMeta._instances.pop(RssTaskService, None)

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

        service = RssTaskService(
            config_repo=config_repo,
            rss_repo=MagicMock(),
            rsshelper=MagicMock(),
            message=MagicMock(),
            searcher=MagicMock(),
            filter_=MagicMock(),
            media=MagicMock(),
            downloader=MagicMock(),
            subscribe=MagicMock(),
        )
        with patch.object(service, "stop_service"):
            service.init_config()

        assert len(service._rss_parsers) == 1
        assert service._rss_parsers[0]["id"] == 1
        assert service._rss_parsers[0]["name"] == "TestParser"

from unittest.mock import MagicMock

import pytest

from app.services.userrss_service import UserRssService


@pytest.fixture
def svc():
    mock_checker = MagicMock()
    return UserRssService(rss_checker=mock_checker)


class TestCheckTasks:
    def test_enable_all(self, svc):
        svc.check_tasks(None, "enable")
        svc._checker.check_userrss_task.assert_called_once_with(state=True)

    def test_disable_ids(self, svc):
        svc.check_tasks([1, 2], "disable")
        assert svc._checker.check_userrss_task.call_count == 2

    def test_unknown_flag(self, svc):
        svc.check_tasks([1], "unknown")
        svc._checker.check_userrss_task.assert_not_called()


class TestDeleteParser:
    def test_success(self, svc):
        svc._checker.delete_userrss_parser.return_value = True
        assert svc.delete_parser(1) is True


class TestDeleteTask:
    def test_success(self, svc):
        svc._checker.delete_userrss_task.return_value = True
        assert svc.delete_task(1) is True


class TestGetParsers:
    def test_ok(self, svc):
        svc._checker.get_userrss_parser.return_value = [{"id": 1}]
        assert svc.get_parsers() == [{"id": 1}]


class TestGetParser:
    def test_ok(self, svc):
        svc._checker.get_userrss_parser.return_value = {"id": 1}
        assert svc.get_parser(1) == {"id": 1}


class TestGetTask:
    def test_ok(self, svc):
        svc._checker.get_rsstask_info.return_value = {"id": 1}
        assert svc.get_task(1) == {"id": 1}


class TestGetTasks:
    def test_ok(self, svc):
        svc._checker.get_rsstask_info.return_value = [{"id": 1}]
        assert svc.get_tasks() == [{"id": 1}]


class TestGetArticles:
    def test_with_articles(self, svc):
        svc._checker.get_rsstask_info.return_value = {"uses": "D", "address": ["a1"]}
        svc._checker.get_rss_articles.return_value = [{"title": "t1"}]
        dto = svc.get_articles(1)
        assert dto.articles == [{"title": "t1"}]
        assert dto.count == 1
        assert dto.uses == "D"
        assert dto.address_count == 1

    def test_empty(self, svc):
        svc._checker.get_rsstask_info.return_value = {}
        svc._checker.get_rss_articles.return_value = []
        dto = svc.get_articles(1)
        assert dto.articles == []
        assert dto.count == 0


class TestGetHistory:
    def test_with_history(self, svc):
        h = MagicMock()
        h.TITLE = "t1"
        h.DOWNLOADER = "d1"
        h.DATE = "2024-01-01"
        svc._checker.get_userrss_task_history.return_value = [h]
        dto = svc.get_history(1)
        assert dto.count == 1
        assert dto.downloads[0]["title"] == "t1"

    def test_empty(self, svc):
        svc._checker.get_userrss_task_history.return_value = []
        dto = svc.get_history(1)
        assert dto.count == 0


class TestTestArticle:
    def test_no_media(self, svc):
        svc._checker.test_rss_articles.return_value = (None, False, False)
        dto = svc.test_article("1", "title")
        assert dto.name == "无法识别"

    def test_unrecognizable(self, svc):
        svc._checker.test_rss_articles.return_value = None
        dto = svc.test_article("1", "title")
        assert dto.name == "无法识别"

    def test_success(self, svc):
        mock_media = MagicMock()
        mock_media.get_name.return_value = "Test Media"
        svc._checker.test_rss_articles.return_value = (mock_media, True, False)
        dto = svc.test_article("1", "title")
        assert dto.name == "Test Media"
        assert dto.match_flag is True
        assert dto.exist_flag is False
        assert dto.media_dict is not None


class TestCheckArticles:
    def test_success(self, svc):
        svc._checker.check_rss_articles.return_value = True
        assert svc.check_articles("1", "D", ["a1"]) is True


class TestDownloadArticles:
    def test_success(self, svc):
        svc._checker.download_rss_articles.return_value = True
        assert svc.download_articles("1", ["a1"]) is True


class TestRunTask:
    def test_ok(self, svc):
        svc.run_task("1")
        svc._checker.check_task_rss.assert_called_once_with("1")


class TestUpdateParser:
    def test_success(self, svc):
        svc._checker.update_userrss_parser.return_value = True
        assert svc.update_parser({"id": 1}) is True


class TestUpdateTask:
    def test_no_address_parser(self, svc):
        dto = svc.update_task({"uses": "D"})
        assert dto.success is False

    def test_download_type(self, svc):
        svc._checker.update_userrss_task.return_value = True
        dto = svc.update_task(
            {
                "uses": "D",
                "address_parser": {"address_0": "http://a.com", "parser_0": "p1"},
                "id": 1,
                "name": "task",
                "recognization": "Y",
            }
        )
        assert dto.success is True
        call_args = svc._checker.update_userrss_task.call_args[0][0]
        assert call_args["uses"] == "D"
        assert call_args.get("recognization") == "Y"

    def test_rss_type(self, svc):
        svc._checker.update_userrss_task.return_value = True
        dto = svc.update_task(
            {"uses": "R", "address_parser": {"address_0": "http://a.com"}, "sites": {"rss_sites": []}}
        )
        assert dto.success is True
        call_args = svc._checker.update_userrss_task.call_args[0][0]
        assert call_args["sites"] == {"rss_sites": []}

    def test_invalid_uses(self, svc):
        dto = svc.update_task({"uses": "X", "address_parser": {"address_0": "http://a.com"}})
        assert dto.success is False

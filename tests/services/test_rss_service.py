import json
import pytest
from unittest.mock import patch, MagicMock

from app.services.rss_service import RssParserEngine, RssTaskService
from app.utils.types import MediaType


class TestRssParserEngine:
    def test_parse_items_xml(self):
        rss_parser = {
            "type": "XML",
            "format": json.dumps({
                "list": "//item",
                "item": {
                    "title": {"path": "title/text()"},
                    "link": {"path": "link/text()"}
                }
            })
        }
        rss_text = """<?xml version="1.0"?>
        <rss>
            <item><title>Test 1</title><link>http://a/1</link></item>
            <item><title>Test 2</title><link>http://a/2</link></item>
        </rss>
        """
        result = RssParserEngine.parse_items(rss_parser, rss_text, 1)
        assert len(result) == 2
        assert result[0]["title"] == "Test 1"
        assert result[0]["link"] == "http://a/1"
        assert result[0]["address_index"] == 1

    def test_parse_items_json(self):
        rss_parser = {
            "type": "JSON",
            "format": json.dumps({
                "list": "$.data.list",
                "item": {
                    "title": {"path": "$.title"},
                    "size": {"path": "$.size"}
                }
            })
        }
        rss_text = json.dumps({
            "data": {
                "list": [
                    {"title": "Item A", "size": 1024},
                    {"title": "Item B", "size": 2048}
                ]
            }
        })
        result = RssParserEngine.parse_items(rss_parser, rss_text, 2)
        assert len(result) == 2
        assert result[0]["title"] == "Item A"
        assert result[0]["size"] == 1024
        assert result[0]["address_index"] == 2

    def test_parse_items_unknown_type(self):
        rss_parser = {"type": "YAML", "format": "{}"}
        result = RssParserEngine.parse_items(rss_parser, "text", 1)
        assert result == []

    def test_parse_items_xml_invalid(self):
        rss_parser = {
            "type": "XML",
            "format": json.dumps({"list": "//item", "item": {"title": {"path": "title/text()"}}})
        }
        with pytest.raises(ValueError):
            RssParserEngine.parse_items(rss_parser, "not xml", 1)

    def test_parse_items_json_invalid(self):
        rss_parser = {
            "type": "JSON",
            "format": json.dumps({"list": "$.data", "item": {"title": {"path": "$.title"}}})
        }
        with pytest.raises(ValueError):
            RssParserEngine.parse_items(rss_parser, "not json", 1)


class TestRssTaskService:
    @pytest.fixture
    def svc(self):
        with patch.object(RssTaskService, "init_config", lambda self: None):
            service = RssTaskService.__new__(RssTaskService)
            service._rss_tasks = []
            service._rss_parsers = []
            service.rsshelper = MagicMock()
            service.dbhelper = MagicMock()
            service.downloader = MagicMock()
            service.media = MagicMock()
            service.filter = MagicMock()
            service.subscribe = MagicMock()
            yield service

    def test_get_rsstask_info_by_id(self, svc):
        svc._rss_tasks = [
            {"id": 1, "name": "task1"},
            {"id": 2, "name": "task2"}
        ]
        assert svc.get_rsstask_info(taskid=1)["name"] == "task1"
        assert svc.get_rsstask_info(taskid="2")["name"] == "task2"
        # 旧实现：数字但找不到时返回全部列表，保持兼容
        assert svc.get_rsstask_info(taskid=99) == svc._rss_tasks
        assert svc.get_rsstask_info(taskid="not_a_number") == {}

    def test_get_rsstask_info_all(self, svc):
        svc._rss_tasks = [{"id": 1, "name": "task1"}]
        assert svc.get_rsstask_info() == svc._rss_tasks

    def test_is_article_processed_download(self, svc):
        svc.rsshelper.is_rssd_by_simple.return_value = True
        assert svc.is_article_processed("D", "Title", "2024", "http://link") is True
        svc.rsshelper.is_rssd_by_simple.assert_called_once_with("Title 2024", "http://link")

    def test_is_article_processed_subscribe(self, svc):
        svc.rsshelper.is_rssd_by_simple.return_value = False
        assert svc.is_article_processed("R", "Title", None, None) is False
        svc.rsshelper.is_rssd_by_simple.assert_called_once_with("Title", "Title")

    def test_check_rss_articles_set_finished_download(self, svc):
        svc._rss_tasks = [{"id": 1, "uses": "D"}]
        svc.rsshelper.is_rssd_by_simple.return_value = False
        articles = [{"title": "A", "enclosure": "e1", "year": "2024"}]
        assert svc.check_rss_articles(1, "set_finished", articles) is True
        svc.rsshelper.simple_insert_rss_torrents.assert_called_once_with("A 2024", "e1")

    def test_check_rss_articles_set_finished_subscribe(self, svc):
        svc._rss_tasks = [{"id": 1, "uses": "R"}]
        svc.rsshelper.is_rssd_by_simple.return_value = False
        articles = [{"title": "B", "enclosure": "e2", "year": None}]
        assert svc.check_rss_articles(1, "set_finished", articles) is True
        svc.rsshelper.simple_insert_rss_torrents.assert_called_once_with("B", "B")

    def test_check_rss_articles_set_unfinish(self, svc):
        svc._rss_tasks = [{"id": 1, "uses": "D"}]
        articles = [{"title": "C", "enclosure": "e3", "year": "2023"}]
        assert svc.check_rss_articles(1, "set_unfinish", articles) is True
        svc.rsshelper.simple_delete_rss_torrents.assert_called_once_with("C 2023", "e3")

    def test_check_rss_articles_invalid_flag(self, svc):
        svc._rss_tasks = [{"id": 1, "uses": "D"}]
        assert svc.check_rss_articles(1, "invalid", []) is False

    def test_download_rss_articles_success(self, svc):
        svc._rss_tasks = [{"id": 1, "save_path": "/tmp", "download_setting": "", "proxy": False}]
        media_mock = MagicMock()
        svc.media.get_media_info.return_value = media_mock
        svc.downloader.download.return_value = (1, True, "")
        svc.downloader.get_downloader_conf.return_value = {"name": "qb"}

        articles = [{"title": "Movie", "enclosure": "magnet:1"}]
        assert svc.download_rss_articles(1, articles) is True
        svc.media.get_media_info.assert_called_once_with(title="Movie")
        media_mock.set_torrent_info.assert_called_once_with(enclosure="magnet:1")
        svc.downloader.download.assert_called_once()
        svc.rsshelper.insert_rss_torrents.assert_called_once_with(media_mock)
        svc.dbhelper.insert_userrss_task_history.assert_called_once_with(1, media_mock.org_string, "qb")

    def test_download_rss_articles_failure(self, svc):
        svc._rss_tasks = [{"id": 1, "save_path": "/tmp", "download_setting": "", "proxy": False}]
        media_mock = MagicMock()
        svc.media.get_media_info.return_value = media_mock
        svc.downloader.download.return_value = (1, False, "error")
        svc.downloader.get_downloader_conf.return_value = {"name": "qb"}

        articles = [{"title": "Movie", "enclosure": "magnet:1"}]
        assert svc.download_rss_articles(1, articles) is False

    def test_download_rss_articles_no_task(self, svc):
        assert svc.download_rss_articles(1, []) is None

    def test_get_userrss_mediainfos(self, svc):
        task1 = MagicMock()
        task1.MEDIAINFOS = '[{"tmdb_id": 1}]'
        task2 = MagicMock()
        task2.MEDIAINFOS = None
        svc.dbhelper.get_userrss_tasks.return_value = [task1, task2]
        result = svc.get_userrss_mediainfos()
        assert result == [{"tmdb_id": 1}]

    def test_delete_userrss_task(self, svc):
        svc.dbhelper.delete_userrss_task.return_value = True
        svc.init_config = MagicMock()
        assert svc.delete_userrss_task(1) is True
        svc.dbhelper.delete_userrss_task.assert_called_once_with(1)
        svc.init_config.assert_called_once()

    def test_update_userrss_task(self, svc):
        svc.dbhelper.update_userrss_task.return_value = True
        svc.init_config = MagicMock()
        item = {"name": "test"}
        assert svc.update_userrss_task(item) is True
        svc.dbhelper.update_userrss_task.assert_called_once_with(item)

    def test_check_userrss_task(self, svc):
        svc.dbhelper.check_userrss_task.return_value = True
        svc.init_config = MagicMock()
        assert svc.check_userrss_task(tid=1, state=True) is True
        svc.dbhelper.check_userrss_task.assert_called_once_with(1, True)

    def test_delete_userrss_parser(self, svc):
        svc.dbhelper.delete_userrss_parser.return_value = True
        svc.init_config = MagicMock()
        assert svc.delete_userrss_parser(1) is True
        svc.dbhelper.delete_userrss_parser.assert_called_once_with(1)

    def test_update_userrss_parser(self, svc):
        svc.dbhelper.update_userrss_parser.return_value = True
        svc.init_config = MagicMock()
        item = {"name": "parser"}
        assert svc.update_userrss_parser(item) is True
        svc.dbhelper.update_userrss_parser.assert_called_once_with(item)

    def test_get_userrss_task_history(self, svc):
        svc.dbhelper.get_userrss_task_history.return_value = [{"TITLE": "A"}]
        assert svc.get_userrss_task_history(1) == [{"TITLE": "A"}]

    def test_get_userrss_parser_by_id(self, svc):
        svc._rss_parsers = [{"id": 1, "name": "p1"}, {"id": 2, "name": "p2"}]
        assert svc.get_userrss_parser(1)["name"] == "p1"
        assert svc.get_userrss_parser(99) == {}

    def test_get_userrss_parser_all(self, svc):
        svc._rss_parsers = [{"id": 1}]
        assert svc.get_userrss_parser() == svc._rss_parsers

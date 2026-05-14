import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.rss_service import (
    RssParserEngine,
    RssSubscriptionService,
    RssTaskService,
)
from app.utils.types import MediaType


class TestRssParserEngine:
    def test_parse_items_xml(self):
        rss_parser = {
            "type": "XML",
            "format": json.dumps(
                {"list": "//item", "item": {"title": {"path": "title/text()"}, "link": {"path": "link/text()"}}}
            ),
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
            "format": json.dumps(
                {"list": "$.data.list", "item": {"title": {"path": "$.title"}, "size": {"path": "$.size"}}}
            ),
        }
        rss_text = json.dumps(
            {"data": {"list": [{"title": "Item A", "size": 1024}, {"title": "Item B", "size": 2048}]}}
        )
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
            "format": json.dumps({"list": "//item", "item": {"title": {"path": "title/text()"}}}),
        }
        with pytest.raises(ValueError):
            RssParserEngine.parse_items(rss_parser, "not xml", 1)

    def test_parse_items_json_invalid(self):
        rss_parser = {"type": "JSON", "format": json.dumps({"list": "$.data", "item": {"title": {"path": "$.title"}}})}
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
            service.config_repo = MagicMock()
            service.rss_repo = MagicMock()
            service.downloader = MagicMock()
            service.media = MagicMock()
            service.filter = MagicMock()
            service.subscribe = MagicMock()
            yield service

    def test_get_rsstask_info_by_id(self, svc):
        svc._rss_tasks = [{"id": 1, "name": "task1"}, {"id": 2, "name": "task2"}]
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
        svc.config_repo.insert_userrss_task_history.assert_called_once_with(1, media_mock.org_string, "qb")

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
        svc.config_repo.get_userrss_tasks.return_value = [task1, task2]
        result = svc.get_userrss_mediainfos()
        assert result == [{"tmdb_id": 1}]

    def test_delete_userrss_task(self, svc):
        svc.config_repo.delete_userrss_task.return_value = True
        svc.init_config = MagicMock()
        assert svc.delete_userrss_task(1) is True
        svc.config_repo.delete_userrss_task.assert_called_once_with(1)
        svc.init_config.assert_called_once()

    def test_update_userrss_task(self, svc):
        svc.config_repo.update_userrss_task.return_value = True
        svc.init_config = MagicMock()
        item = {"name": "test"}
        assert svc.update_userrss_task(item) is True
        svc.config_repo.update_userrss_task.assert_called_once_with(item)

    def test_check_userrss_task(self, svc):
        svc.config_repo.check_userrss_task.return_value = True
        svc.init_config = MagicMock()
        assert svc.check_userrss_task(tid=1, state=True) is True
        svc.config_repo.check_userrss_task.assert_called_once_with(1, True)

    def test_delete_userrss_parser(self, svc):
        svc.config_repo.delete_userrss_parser.return_value = True
        svc.init_config = MagicMock()
        assert svc.delete_userrss_parser(1) is True
        svc.config_repo.delete_userrss_parser.assert_called_once_with(1)

    def test_update_userrss_parser(self, svc):
        svc.config_repo.update_userrss_parser.return_value = True
        svc.init_config = MagicMock()
        item = {"name": "parser"}
        assert svc.update_userrss_parser(item) is True
        svc.config_repo.update_userrss_parser.assert_called_once_with(item)

    def test_get_userrss_task_history(self, svc):
        svc.config_repo.get_userrss_task_history.return_value = [{"TITLE": "A"}]
        assert svc.get_userrss_task_history(1) == [{"TITLE": "A"}]

    def test_get_userrss_parser_by_id(self, svc):
        svc._rss_parsers = [{"id": 1, "name": "p1"}, {"id": 2, "name": "p2"}]
        assert svc.get_userrss_parser(1)["name"] == "p1"
        assert svc.get_userrss_parser(99) == {}

    def test_get_userrss_parser_all(self, svc):
        svc._rss_parsers = [{"id": 1}]
        assert svc.get_userrss_parser() == svc._rss_parsers


class TestRssSubscriptionService:
    @pytest.fixture
    def svc(self):
        mock_subscribe = MagicMock()
        mock_rss = MagicMock()
        mock_checker = MagicMock()
        return RssSubscriptionService(subscribe=mock_subscribe, rss=mock_rss, rss_checker=mock_checker)

    def test_add_rss_media_single(self, svc):
        mock_media_info = MagicMock()
        mock_media_info.tmdb_id = "456"
        svc._subscribe.add_rss_subscribe.side_effect = lambda **kwargs: (0, "成功", mock_media_info)
        svc._subscribe.get_subscribe_id.return_value = "123"
        result = svc.add_rss_media(
            {
                "name": "Test",
                "year": "2024",
                "type": "MOV",
                "season": 1,
                "in_form": "manual",
                "rssid": None,
                "keyword": None,
                "fuzzy_match": None,
                "mediaid": None,
                "rss_sites": None,
                "search_sites": None,
                "over_edition": None,
                "filter_restype": None,
                "filter_pix": None,
                "filter_team": None,
                "filter_rule": None,
                "filter_include": None,
                "filter_exclude": None,
                "save_path": None,
                "download_setting": None,
                "total_ep": None,
                "current_ep": None,
                "page": 1,
            }
        )
        assert result.code == 0
        assert result.rssid == "123"
        assert result.media_info == mock_media_info
        svc._subscribe.add_rss_subscribe.assert_called_once()

    def test_add_rss_media_multi_season(self, svc):
        svc._subscribe.add_rss_subscribe.side_effect = lambda **kwargs: (0, "成功", None)
        svc._subscribe.get_subscribe_id.return_value = "456"
        result = svc.add_rss_media(
            {
                "name": "Test",
                "year": "2024",
                "type": "TV",
                "season": [1, 2],
                "in_form": "auto",
                "rssid": None,
                "keyword": None,
                "fuzzy_match": None,
                "mediaid": None,
                "rss_sites": None,
                "search_sites": None,
                "over_edition": None,
                "filter_restype": None,
                "filter_pix": None,
                "filter_team": None,
                "filter_rule": None,
                "filter_include": None,
                "filter_exclude": None,
                "save_path": None,
                "download_setting": None,
                "page": 1,
            }
        )
        assert result.code == 0
        assert svc._subscribe.add_rss_subscribe.call_count == 2

    def test_add_rss_media_failure(self, svc):
        svc._subscribe.add_rss_subscribe.return_value = (-1, "失败", None)
        result = svc.add_rss_media(
            {
                "name": "Test",
                "year": "2024",
                "type": "MOV",
                "season": 1,
                "in_form": "manual",
                "rssid": None,
                "keyword": None,
                "fuzzy_match": None,
                "mediaid": None,
                "rss_sites": None,
                "search_sites": None,
                "over_edition": None,
                "filter_restype": None,
                "filter_pix": None,
                "filter_team": None,
                "filter_rule": None,
                "filter_include": None,
                "filter_exclude": None,
                "save_path": None,
                "download_setting": None,
                "total_ep": None,
                "current_ep": None,
                "page": 1,
            }
        )
        assert result.code == -1
        assert result.msg == "失败"

    def test_re_rss_history_success(self, svc):
        mock_rec = MagicMock()
        mock_rec.NAME = "Test"
        mock_rec.YEAR = "2024"
        mock_rec.SEASON = "S01"
        mock_rec.TMDBID = "123"
        mock_rec.TOTAL = 10
        mock_rec.START = 1
        svc._rss.get_rss_history.return_value = [mock_rec]
        svc._subscribe.add_rss_subscribe.return_value = (0, "成功", None)
        code, msg = svc.re_rss_history("1", "MOV")
        assert code == 0

    def test_re_rss_history_not_found(self, svc):
        svc._rss.get_rss_history.return_value = []
        code, msg = svc.re_rss_history("1", "MOV")
        assert code == -1
        assert "不存在" in msg

    def test_remove_rss_media_movie(self, svc):
        svc.remove_rss_media("Test Movie", "MOV", "2024", None, "1", "123")
        svc._subscribe.delete_subscribe.assert_called_once_with(
            mtype=MediaType.MOVIE, title="Test Movie", year="2024", rssid="1", tmdbid="123"
        )

    def test_remove_rss_media_tv(self, svc):
        with patch("app.services.rss_service.meta_info") as MockMeta:
            MockMeta.return_value.get_name.return_value = "Test Tv"
            svc.remove_rss_media("Test TV", "TV", "2024", 1, "1", "123")
            svc._subscribe.delete_subscribe.assert_called_once_with(
                mtype=MediaType.TV, title="Test Tv", season=1, rssid="1", tmdbid="123"
            )

    def test_remove_rss_media_non_digit_tmdbid(self, svc):
        svc.remove_rss_media("Test", "MOV", "2024", None, "1", "tv-123")
        svc._subscribe.delete_subscribe.assert_called_once_with(
            mtype=MediaType.MOVIE, title="Test", year="2024", rssid="1", tmdbid=None
        )

    def test_get_rss_detail_movie(self, svc):
        svc._subscribe.get_subscribe_movies.return_value = {"1": {"name": "Test", "id": "1"}}
        result = svc.get_rss_detail("1", "MOV")
        assert result.detail["type"] == "MOV"

    def test_get_rss_detail_tv(self, svc):
        svc._subscribe.get_subscribe_tvs.return_value = {"1": {"name": "Test", "id": "1"}}
        result = svc.get_rss_detail("1", "TV")
        assert result.detail["type"] == "TV"

    def test_get_rss_detail_not_found(self, svc):
        svc._subscribe.get_subscribe_movies.return_value = {}
        result = svc.get_rss_detail("1", "MOV")
        assert result is None

    def test_get_default_rss_setting_tv(self, svc):
        svc._subscribe.default_rss_setting_tv = {"quality": "1080p"}
        assert svc.get_default_rss_setting("TV") == {"quality": "1080p"}

    def test_get_default_rss_setting_mov(self, svc):
        svc._subscribe.default_rss_setting_mov = {"quality": "4K"}
        assert svc.get_default_rss_setting("MOV") == {"quality": "4K"}

    def test_get_default_rss_setting_other(self, svc):
        assert svc.get_default_rss_setting("ANI") == {}

    def test_get_movie_rss_items(self, svc):
        svc._subscribe.get_subscribe_movies.return_value = {
            "1": {"tmdbid": "123", "id": "1"},
            "2": {"tmdbid": "", "id": "2"},
        }
        result = svc.get_movie_rss_items()
        assert len(result) == 1
        assert result[0]["id"] == "123"

    def test_get_tv_rss_items(self, svc):
        svc._subscribe.get_subscribe_tvs.return_value = {
            "1": {"tmdbid": "123", "id": "1", "season": "S01", "name": "Test"},
            "2": {"tmdbid": "", "id": "2", "season": "S02"},
        }
        svc._rss_checker.get_userrss_mediainfos.return_value = []
        result = svc.get_tv_rss_items()
        assert len(result) == 1
        assert result[0]["season"] == 1

    def test_get_tv_rss_items_dedup(self, svc):
        svc._subscribe.get_subscribe_tvs.return_value = {
            "1": {"tmdbid": "123", "id": "1", "season": "S01", "name": "Test"},
        }
        svc._rss_checker.get_userrss_mediainfos.return_value = [
            {"id": "123", "season": 1, "rssid": "2", "name": "Test"},
            {"id": "123", "season": 1, "rssid": "3", "name": "Test"},
        ]
        result = svc.get_tv_rss_items()
        assert len(result) == 1

    def test_get_movie_rss_list(self, svc):
        svc._subscribe.get_subscribe_movies.return_value = {"1": {"name": "A"}}
        assert svc.get_movie_rss_list() == {"1": {"name": "A"}}

    def test_get_tv_rss_list(self, svc):
        svc._subscribe.get_subscribe_tvs.return_value = {"1": {"name": "B"}}
        assert svc.get_tv_rss_list() == {"1": {"name": "B"}}

    def test_get_rss_history(self, svc):
        mock_rec = MagicMock()
        mock_rec.as_dict.return_value = {"id": 1}
        svc._rss.get_rss_history.return_value = [mock_rec]
        result = svc.get_rss_history("MOV")
        assert result == [{"id": 1}]

    def test_delete_rss_history(self, svc):
        svc.delete_rss_history("1")
        svc._rss.delete_rss_history.assert_called_once_with(rssid="1")

    def test_refresh_rss_movie(self, svc):
        with patch("app.helper.ThreadHelper") as MockTh:
            svc.refresh_rss("MOV", "1")
            MockTh().start_thread.assert_called_once()

    def test_refresh_rss_tv(self, svc):
        with patch("app.helper.ThreadHelper") as MockTh:
            svc.refresh_rss("TV", "1")
            MockTh().start_thread.assert_called_once()

    def test_truncate_rss_history(self, svc):
        with patch("app.helper.RssHelper") as MockHelper:
            mock_inst = MagicMock()
            MockHelper.return_value = mock_inst
            svc.truncate_rss_history()
            mock_inst.truncate_rss_history.assert_called_once()
            svc._subscribe.truncate_rss_episodes.assert_called_once()

    def test_get_ical_events(self, svc):
        svc._subscribe.get_subscribe_movies.return_value = {"1": {"tmdbid": "123", "id": "1"}}
        svc._subscribe.get_subscribe_tvs.return_value = {
            "1": {"tmdbid": "456", "id": "1", "season": "S01", "name": "Test"}
        }
        svc._rss_checker.get_userrss_mediainfos.return_value = []
        with patch("app.services.media_service.MediaInfoService") as MockMedia:
            mock_media_svc = MagicMock()
            mock_media_svc.get_movie_calendar.return_value = {"id": "123", "title": "Movie"}
            mock_media_svc.get_tv_calendar.return_value = [{"id": "456", "title": "TV"}]
            MockMedia.return_value = mock_media_svc
            result = svc.get_ical_events()
            assert len(result) == 2

"""SearchPaginationManager 单元测试."""

from unittest.mock import MagicMock

import pytest

from app.services.search_pagination import SearchPaginationManager


@pytest.fixture
def manager():
    return SearchPaginationManager(message=MagicMock())


class TestSearchPaginationManager:
    def test_set_and_get_media_cache(self, manager):
        manager.set_media_cache("u1", [{"id": 1}], "MOVIE")
        assert manager.get_media_cache("u1") == [{"id": 1}]
        assert manager.get_media_type("u1") == "MOVIE"

    def test_clear_media_cache(self, manager):
        manager.set_media_cache("u1", [{"id": 1}], "MOVIE")
        manager.set_search_results("u1", [{"name": "x"}])
        manager.clear_media_cache("u1")
        assert manager.get_media_cache("u1") is None
        assert manager.get_page("u1") is None

    def test_set_search_results(self, manager):
        manager.set_search_results("u1", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10], title="Results")
        page = manager.get_page("u1")
        assert page["total"] == 10
        assert page["page"] == 1
        assert page["media_title"] == "Results"
        result = manager.get_current_page_items("u1")
        assert result["total_pages"] == 2
        assert result["title"] == "Results"

    def test_navigate_next_and_prev(self, manager):
        manager.set_search_results("u1", list(range(20)))
        result = manager.navigate("u1", "n")
        assert result["page"] == 2
        assert result["items"] == list(range(8, 16))
        result = manager.navigate("u1", "p")
        assert result["page"] == 1
        assert result["items"] == list(range(8))

    def test_navigate_boundary(self, manager):
        manager.set_search_results("u1", list(range(5)))
        assert manager.navigate("u1", "p") == {"error": "已经是第一页了"}
        manager.set_search_results("u1", list(range(8)))
        assert manager.navigate("u1", "n") == {"error": "已经是最后一页了"}

    def test_navigate_invalid(self, manager):
        manager.set_search_results("u1", list(range(10)))
        assert manager.navigate("u1", "x") is None
        assert manager.navigate("u2", "n") is None

    def test_select_item(self, manager):
        manager.set_search_results("u1", list(range(20)))
        assert manager.select_item("u1", 1) == 0
        manager.navigate("u1", "n")
        assert manager.select_item("u1", 1) == 8
        assert manager.select_item("u1", 100) is None

    def test_get_current_page_items(self, manager):
        manager.set_search_results("u1", list(range(5)))
        result = manager.get_current_page_items("u1")
        assert result["items"] == list(range(5))
        assert result["total_pages"] == 1

    def test_send_page_message(self, manager):
        item = MagicMock()
        item.TORRENT_NAME = "t1"
        item.SIZE = 1024
        item.SEEDERS = 5
        item.SITE = "s1"
        manager.set_search_results("u1", [item])
        manager.send_page_message("telegram", "u1")
        manager._message.send_channel_msg.assert_called_once()
        args = manager._message.send_channel_msg.call_args.kwargs
        assert "telegram" == args["channel"]
        assert "u1" == args["user_id"]
        assert "t1" in args["text"]

    def test_send_page_message_no_results(self, manager):
        manager.send_page_message("telegram", "u1")
        manager._message.send_channel_msg.assert_called_once()
        assert "没有可用的搜索结果分页" in manager._message.send_channel_msg.call_args.kwargs["title"]

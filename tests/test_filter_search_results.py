#!/usr/bin/env python3
"""
测试搜索结果过滤的三阶段并发 TMDB 查询重构
"""

import time
import unittest
from unittest.mock import Mock, patch

from app.indexer.client._base import _IIndexClient
from app.utils.types import MediaType


class MockIndexClient(_IIndexClient):
    client_id = "mock"
    client_type = "mock"
    client_name = "Mock"

    def match(self, ctype):
        return True

    def get_status(self):
        return True

    def get_type(self):
        return self.client_type

    def get_client_id(self):
        return self.client_id

    def get_indexers(self):
        return []

    def search(self, order_seq, indexer, keyword, filter_args):
        return []


class TestFilterSearchResults(unittest.TestCase):
    def setUp(self):
        self.client = MockIndexClient()
        self.indexer = Mock()
        self.indexer.name = "TestSite"
        self.indexer.public = False

        # match_media
        self.match_media = Mock()
        self.match_media.imdb_id = None
        self.match_media.tmdb_id = "12345"
        self.match_media.title = "Test Title"
        self.match_media.cn_name = "测试标题"
        self.match_media.en_name = "Test Title"
        self.match_media.original_title = "Test Title"
        self.match_media.type = MediaType.MOVIE
        self.match_media.over_edition = False
        self.match_media.res_order = None

    @patch.object(_IIndexClient, "_quick_name_match")
    @patch.object(MockIndexClient, "media")
    def test_concurrent_identify(self, mock_media, mock_quick_match):
        """测试需要 TMDB 识别的候选会被并发查询"""
        mock_quick_match.return_value = False

        call_times = []

        def slow_get_media_info(title, subtitle=None, chinese=False):
            call_times.append(title)
            time.sleep(0.2)
            info = Mock()
            info.tmdb_info = {"id": "12345"}
            info.tmdb_id = "12345"
            info.type = MediaType.MOVIE
            info.title = title
            info.get_name.return_value = title
            info.get_title_string.return_value = title
            info.get_season_episode_string.return_value = ""
            return info

        mock_media.get_media_info.side_effect = slow_get_media_info

        result_array = [
            {
                "title": f"Movie {i}",
                "description": "",
                "size": 1000,
                "seeders": 1,
                "uploadvolumefactor": 1.0,
                "downloadvolumefactor": 1.0,
                "enclosure": "url",
            }
            for i in range(6)
        ]

        start = time.time()
        self.client.filter_search_results(
            result_array=result_array,
            order_seq=1,
            indexer=self.indexer,
            filter_args={},
            match_media=self.match_media,
            start_time=Mock(),
        )
        elapsed = time.time() - start

        # 6 个并发查询，每个 0.2s，如果串行需要 >= 1.2s，并发应在 0.4s 内完成
        self.assertLess(elapsed, 0.6, f"TMDB 查询应该是并发的，实际耗时 {elapsed:.2f}s")
        self.assertEqual(len(call_times), 6, "每个候选都应该被识别一次")

    @patch.object(_IIndexClient, "_quick_name_match")
    @patch.object(MockIndexClient, "media")
    def test_cache_hit_skip_tmdb(self, mock_media, mock_quick_match):
        """测试缓存命中时不会重复查询 TMDB"""
        mock_quick_match.return_value = False
        mock_media.get_media_info.return_value = Mock(
            tmdb_info={"id": "12345"},
            tmdb_id="12345",
            type=MediaType.MOVIE,
            get_name=lambda: "Cached",
            get_title_string=lambda: "Cached",
            get_season_episode_string=lambda: "",
        )

        result_array = [
            {
                "title": "Cached Movie",
                "description": "",
                "size": 1000,
                "seeders": 1,
                "uploadvolumefactor": 1.0,
                "downloadvolumefactor": 1.0,
                "enclosure": "url",
            }
        ]

        # 第一次调用
        self.client.filter_search_results(
            result_array=result_array,
            order_seq=1,
            indexer=self.indexer,
            filter_args={},
            match_media=self.match_media,
            start_time=Mock(),
        )

        # 第二次调用，缓存已存在
        self.client.filter_search_results(
            result_array=result_array,
            order_seq=1,
            indexer=self.indexer,
            filter_args={},
            match_media=self.match_media,
            start_time=Mock(),
        )

        self.assertEqual(mock_media.get_media_info.call_count, 1, "缓存命中后不应再次调用 get_media_info")

    @patch.object(_IIndexClient, "_quick_name_match")
    @patch.object(MockIndexClient, "media")
    def test_quick_name_match_skip_tmdb(self, mock_media, mock_quick_match):
        """测试快速名称匹配成功时跳过 TMDB 查询"""
        mock_quick_match.return_value = True

        result_array = [
            {
                "title": "Quick Match",
                "description": "",
                "size": 1000,
                "seeders": 1,
                "uploadvolumefactor": 1.0,
                "downloadvolumefactor": 1.0,
                "enclosure": "url",
            }
        ]

        self.client.filter_search_results(
            result_array=result_array,
            order_seq=1,
            indexer=self.indexer,
            filter_args={},
            match_media=self.match_media,
            start_time=Mock(),
        )

        mock_media.get_media_info.assert_not_called()


if __name__ == "__main__":
    unittest.main()

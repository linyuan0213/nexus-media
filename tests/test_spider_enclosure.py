"""
Spider enclosure 单元测试 — 验证磁力链接空白前缀问题
"""

import sys
from unittest.mock import MagicMock

from app.indexer.client._spider import TorrentSpider

sys.modules["log"] = MagicMock()


class TestSpiderGetdownload:
    def test_magnet_with_leading_space(self):
        """磁力链接有前导空白时，不应拼接域名"""
        spider = TorrentSpider.__new__(TorrentSpider)
        spider.domain = "https://dmhy.org/"
        spider.fields = {"download": {"selector": "a", "attribute": "href"}}
        spider.torrents_info = {}

        # 模拟 pyquery 返回带有前导空白的 href
        mock_torrent = MagicMock()
        mock_item = MagicMock()
        mock_item.attr.return_value = " magnet:?xt=urn:btih:ABC123"
        mock_torrent.return_value.clone.return_value.items.return_value = [mock_item]

        spider.Getdownload(mock_torrent)
        assert spider.torrents_info["enclosure"] == "magnet:?xt=urn:btih:ABC123"

    def test_relative_path(self):
        """相对路径应拼接域名"""
        spider = TorrentSpider.__new__(TorrentSpider)
        spider.domain = "https://dmhy.org/"
        spider.fields = {"download": {"selector": "a", "attribute": "href"}}
        spider.torrents_info = {}

        mock_torrent = MagicMock()
        mock_item = MagicMock()
        mock_item.attr.return_value = "/download/123.torrent"
        mock_torrent.return_value.clone.return_value.items.return_value = [mock_item]

        spider.Getdownload(mock_torrent)
        assert spider.torrents_info["enclosure"] == "https://dmhy.org/download/123.torrent"

    def test_absolute_http(self):
        """绝对 HTTP URL 不应拼接域名"""
        spider = TorrentSpider.__new__(TorrentSpider)
        spider.domain = "https://dmhy.org/"
        spider.fields = {"download": {"selector": "a", "attribute": "href"}}
        spider.torrents_info = {}

        mock_torrent = MagicMock()
        mock_item = MagicMock()
        mock_item.attr.return_value = "https://other.site/file.torrent"
        mock_torrent.return_value.clone.return_value.items.return_value = [mock_item]

        spider.Getdownload(mock_torrent)
        assert spider.torrents_info["enclosure"] == "https://other.site/file.torrent"

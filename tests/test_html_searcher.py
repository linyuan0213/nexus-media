"""
HtmlSiteSearcher 单元测试 — 验证 enclosure URL 规范化
"""

import sys
from unittest.mock import MagicMock

from app.sites.html_searcher import HtmlSiteSearcher

sys.modules["log"] = MagicMock()


class TestNormalizeHtmlResult:
    def test_magnet_not_prefixed(self):
        """磁力链接不应被拼接域名"""
        searcher = HtmlSiteSearcher.__new__(HtmlSiteSearcher)
        searcher._site = MagicMock()
        searcher._site.domain = "https://mikanani.me"

        item = {"enclosure": "magnet:?xt=urn:btih:abc123"}
        searcher._normalize_html_result(item)
        assert item["enclosure"] == "magnet:?xt=urn:btih:abc123"

    def test_relative_path_prefixed(self):
        """相对路径应拼接域名"""
        searcher = HtmlSiteSearcher.__new__(HtmlSiteSearcher)
        searcher._site = MagicMock()
        searcher._site.domain = "https://example.com"

        item = {"enclosure": "/download/123.torrent"}
        searcher._normalize_html_result(item)
        assert item["enclosure"] == "https://example.com/download/123.torrent"

    def test_http_not_prefixed(self):
        """绝对 HTTP URL 不应被拼接域名"""
        searcher = HtmlSiteSearcher.__new__(HtmlSiteSearcher)
        searcher._site = MagicMock()
        searcher._site.domain = "https://example.com"

        item = {"enclosure": "https://other.site/file.torrent"}
        searcher._normalize_html_result(item)
        assert item["enclosure"] == "https://other.site/file.torrent"

    def test_page_url_relative(self):
        """page_url 相对路径也应拼接域名"""
        searcher = HtmlSiteSearcher.__new__(HtmlSiteSearcher)
        searcher._site = MagicMock()
        searcher._site.domain = "https://example.com"

        item = {"page_url": "/details/123"}
        searcher._normalize_html_result(item)
        assert item["page_url"] == "https://example.com/details/123"

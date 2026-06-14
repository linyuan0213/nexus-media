"""RssHelper 缓存单元测试."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.rss_processor import RssHelper


@pytest.fixture
def helper():
    site_engine = MagicMock()
    site_engine.site_limiter = None
    h = RssHelper(site_engine=site_engine, repo=MagicMock(), cache_ttl=60)
    h._cache.clear()
    return h


class TestRssHelperCache:
    @patch("app.services.rss_processor.HttpClient")
    def test_parse_rssxml_caches_result(self, mock_http_client, helper):
        mock_response = MagicMock()
        mock_response.text = """<?xml version="1.0"?>
<rss>
  <channel>
    <item>
      <title>Test</title>
      <enclosure url="https://example.com/torrent" length="1024"/>
    </item>
  </channel>
</rss>"""
        mock_http_client.return_value.get.return_value = mock_response

        result1 = helper.parse_rssxml("https://example.com/rss", proxy=False)
        result2 = helper.parse_rssxml("https://example.com/rss", proxy=False)
        assert len(result1) == 1
        assert result1 == result2
        mock_http_client.return_value.get.assert_called_once()

    @patch("app.services.rss_processor.HttpClient")
    def test_parse_rssxml_cache_key_includes_proxy(self, mock_http_client, helper):
        mock_response = MagicMock()
        mock_response.text = """<?xml version="1.0"?>
<rss>
  <channel>
    <item>
      <title>Test</title>
      <enclosure url="https://example.com/torrent" length="1024"/>
    </item>
  </channel>
</rss>"""
        mock_http_client.return_value.get.return_value = mock_response

        helper.parse_rssxml("https://example.com/rss", proxy=False)
        helper.parse_rssxml("https://example.com/rss", proxy=True)
        assert mock_http_client.return_value.get.call_count == 2

    @patch("app.services.rss_processor.HttpClient")
    def test_parse_rssxml_different_urls_not_share_cache(self, mock_http_client, helper):
        mock_response = MagicMock()
        mock_response.text = """<?xml version="1.0"?>
<rss>
  <channel>
    <item>
      <title>Test</title>
      <enclosure url="https://example.com/torrent" length="1024"/>
    </item>
  </channel>
</rss>"""
        mock_http_client.return_value.get.return_value = mock_response

        helper.parse_rssxml("https://example.com/rss1", proxy=False)
        helper.parse_rssxml("https://example.com/rss2", proxy=False)
        assert mock_http_client.return_value.get.call_count == 2

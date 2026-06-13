"""SiteResolver 单元测试."""

from unittest.mock import MagicMock, patch

import pytest

from app.sites.site_resolver import SiteResolver


@pytest.fixture
def resolver():
    return SiteResolver(
        cache=MagicMock(),
        site_engine=MagicMock(),
        drissionpage_helper=MagicMock(),
    )


class TestSiteResolver:
    def test_test_connection_site_not_found(self, resolver):
        resolver._cache.get_sites.return_value = None
        ok, msg, seconds = resolver.test_connection(1)
        assert ok is False
        assert msg == "站点获取失败"

    def test_test_connection_site_not_dict(self, resolver):
        resolver._cache.get_sites.return_value = "site"
        ok, msg, seconds = resolver.test_connection(1)
        assert ok is False
        assert msg == "站点不存在"

    def test_test_connection_no_url(self, resolver):
        resolver._cache.get_sites.return_value = {"signurl": "", "rssurl": ""}
        ok, msg, seconds = resolver.test_connection(1)
        assert ok is False
        assert msg == "未配置站点地址"

    def test_test_connection_public_site_success(self, resolver):
        resolver._cache.get_sites.return_value = {"public": True, "rssurl": "https://example.com/rss"}
        resp = MagicMock()
        resp.status_code = 200
        with patch("app.sites.site_resolver.HttpClient") as mock_client:
            mock_client.return_value.get.return_value = resp
            ok, msg, seconds = resolver.test_connection(1)
        assert ok is True
        assert msg == "连接成功"

    def test_test_connection_public_site_failure(self, resolver):
        resolver._cache.get_sites.return_value = {"public": True, "rssurl": "https://example.com/rss"}
        resp = MagicMock()
        resp.status_code = 500
        with patch("app.sites.site_resolver.HttpClient") as mock_client:
            mock_client.return_value.get.return_value = resp
            ok, msg, seconds = resolver.test_connection(1)
        assert ok is False
        assert "500" in msg

    def test_test_connection_no_auth(self, resolver):
        resolver._cache.get_sites.return_value = {"rssurl": "https://example.com/rss"}
        ok, msg, seconds = resolver.test_connection(1)
        assert ok is False
        assert msg == "未配置站点认证信息"

    def test_test_connection_engine(self, resolver):
        resolver._cache.get_sites.return_value = {
            "rssurl": "https://example.com/rss",
            "cookie": "c",
            "ua": "ua",
            "headers": '{"x": 1}',
        }
        resolver._site_engine.get_by_url.return_value = MagicMock()
        resolver._site_engine.test_connection.return_value = (True, "ok", 0.1)
        ok, msg, seconds = resolver.test_connection(1)
        assert ok is True
        resolver._site_engine.test_connection.assert_called_once()

    def test_test_connection_chrome(self, resolver):
        resolver._cache.get_sites.return_value = {
            "rssurl": "https://example.com/rss",
            "cookie": "c",
            "chrome": True,
        }
        resolver._site_engine.get_by_url.return_value = None
        resolver._drissionpage_helper.get_page_html.return_value = """
        <html>
          <a href="/logout">logout</a>
        </html>
        """
        ok, msg, seconds = resolver.test_connection(1)
        assert ok is True
        assert msg == "连接成功"

    def test_test_connection_cookie_expired(self, resolver):
        resolver._cache.get_sites.return_value = {
            "rssurl": "https://example.com/rss",
            "cookie": "c",
        }
        resolver._site_engine.get_by_url.return_value = None
        resp = MagicMock()
        resp.status_code = 200
        resp.text = "<html>login</html>"
        with patch("app.sites.site_resolver.HttpClient") as mock_client:
            mock_client.return_value.get.return_value = resp
            ok, msg, seconds = resolver.test_connection(1)
        assert ok is False
        assert msg == "Cookie失效"

    def test_test_connection_http_failure(self, resolver):
        resolver._cache.get_sites.return_value = {
            "rssurl": "https://example.com/rss",
            "cookie": "c",
        }
        resolver._site_engine.get_by_url.return_value = None
        resp = MagicMock()
        resp.status_code = 403
        with patch("app.sites.site_resolver.HttpClient") as mock_client:
            mock_client.return_value.get.return_value = resp
            ok, msg, seconds = resolver.test_connection(1)
        assert ok is False
        assert "403" in msg

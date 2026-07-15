from unittest.mock import MagicMock, patch

from app.plugin_framework.builtin_plugins.autogenrss.backend.handlers._browser import (
    BrowserRssGenHandler,
)
from app.plugin_framework.builtin_plugins.autogenrss.backend.handlers.base import (
    SiteRssGenContext,
)


class TestBrowserRssGenHandler:
    def _make_ctx(self, **overrides) -> SiteRssGenContext:
        defaults = {
            "site": "test_site",
            "site_id": "test",
            "site_url": "https://test.site/rss",
            "cookie": "uid=1;pass=abc",
            "api_key": None,
            "bearer_token": None,
            "api_key_header": None,
            "ua": "Mozilla/5.0",
            "proxy_url": None,
            "headers": None,
            "raw": {"id": 1},
        }
        defaults.update(overrides)
        return SiteRssGenContext(**defaults)

    def _make_handler(self, config=None):
        plugin_ctx = MagicMock()
        plugin_ctx.site_engine = MagicMock()
        plugin_ctx.site_engine.get_by_id.return_value = None
        return BrowserRssGenHandler(plugin_ctx, None, None, config or {})

    @patch("app.plugin_framework.builtin_plugins.autogenrss.backend.handlers._browser.get_chrome_server_url")
    def test_no_chrome_server(self, mock_get_server):
        mock_get_server.return_value = None
        handler = self._make_handler()
        ctx = self._make_ctx()
        result = handler.generate(ctx)
        assert result.ok is False
        assert "Chrome" in result.msg

    @patch("app.plugin_framework.builtin_plugins.autogenrss.backend.handlers._browser.is_logged_in")
    @patch("app.plugin_framework.builtin_plugins.autogenrss.backend.handlers._browser.get_chrome_server_url")
    @patch("app.plugin_framework.builtin_plugins.autogenrss.backend.handlers._browser.BrowserSession")
    def test_rss_link_parsed(self, mock_session_cls, mock_get_server, mock_is_logged_in):
        mock_get_server.return_value = "http://chrome:9222"
        mock_is_logged_in.return_value = True

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)
        mock_session.navigate.return_value = {"html": '<html><a href="/rss.php?key=1&linktype=dl">rss</a></html>'}
        mock_session_cls.return_value = mock_session

        handler = self._make_handler()
        mock_repo = MagicMock()
        handler._site_repo = mock_repo
        ctx = self._make_ctx()

        result = handler.generate(ctx)

        assert result.ok is True
        mock_repo.update_site_rssurl.assert_called_once()

    @patch("app.plugin_framework.builtin_plugins.autogenrss.backend.handlers._browser.is_logged_in")
    @patch("app.plugin_framework.builtin_plugins.autogenrss.backend.handlers._browser.get_chrome_server_url")
    @patch("app.plugin_framework.builtin_plugins.autogenrss.backend.handlers._browser.BrowserSession")
    def test_cookie_expired(self, mock_session_cls, mock_get_server, mock_is_logged_in):
        mock_get_server.return_value = "http://chrome:9222"
        mock_is_logged_in.return_value = False

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)
        mock_session.navigate.return_value = {"html": '<html><a href="login.php">登录</a></html>'}
        mock_session_cls.return_value = mock_session

        handler = self._make_handler()
        ctx = self._make_ctx()

        result = handler.generate(ctx)

        assert result.ok is False
        assert "Cookie" in result.msg

    @patch("app.plugin_framework.builtin_plugins.autogenrss.backend.handlers._browser.is_logged_in")
    @patch("app.plugin_framework.builtin_plugins.autogenrss.backend.handlers._browser.get_chrome_server_url")
    @patch("app.plugin_framework.builtin_plugins.autogenrss.backend.handlers._browser.BrowserSession")
    def test_no_rss_link(self, mock_session_cls, mock_get_server, mock_is_logged_in):
        mock_get_server.return_value = "http://chrome:9222"
        mock_is_logged_in.return_value = True

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)
        mock_session.navigate.return_value = {"html": "<html><body>hello</body></html>"}
        mock_session_cls.return_value = mock_session

        handler = self._make_handler()
        ctx = self._make_ctx()

        result = handler.generate(ctx)

        assert result.ok is False
        assert "未解析到RSS链接" in result.msg

    @patch("app.plugin_framework.builtin_plugins.autogenrss.backend.handlers._browser.is_logged_in")
    @patch("app.plugin_framework.builtin_plugins.autogenrss.backend.handlers._browser.get_chrome_server_url")
    @patch("app.plugin_framework.builtin_plugins.autogenrss.backend.handlers._browser.BrowserSession")
    def test_empty_html(self, mock_session_cls, mock_get_server, mock_is_logged_in):
        mock_get_server.return_value = "http://chrome:9222"
        mock_is_logged_in.return_value = False

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)
        mock_session.navigate.return_value = {"html": ""}
        mock_session_cls.return_value = mock_session

        handler = self._make_handler()
        ctx = self._make_ctx()

        result = handler.generate(ctx)

        assert result.ok is False
        assert "无法打开网站" in result.msg

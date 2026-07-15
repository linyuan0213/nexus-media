from unittest.mock import MagicMock, patch

from app.plugin_framework.builtin_plugins.autogenrss.backend.handlers.base import (
    SiteRssGenContext,
)
from app.plugin_framework.builtin_plugins.autogenrss.backend.handlers.zhuque import (
    ZhuQue,
)


class TestZhuQueHandler:
    def _make_ctx(self, **overrides) -> SiteRssGenContext:
        defaults = {
            "site": "ZhuQue",
            "site_id": "tnode",
            "site_url": "https://zhuque.in",
            "cookie": "uid=1",
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

    def _make_plugin_ctx(self):
        plugin_ctx = MagicMock()
        site_def = MagicMock()
        site_def.domain = "https://zhuque.in"
        site_def.api = None
        plugin_ctx.site_engine = MagicMock()
        plugin_ctx.site_engine.get_by_id.return_value = site_def
        return plugin_ctx

    @patch("app.sites.utils.is_logged_in")
    def test_cookie_expired(self, mock_is_logged_in):
        mock_is_logged_in.return_value = False
        plugin_ctx = self._make_plugin_ctx()
        handler = ZhuQue(plugin_ctx, None, None)

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.text = '<html><a href="login.php">登录</a></html>'
        mock_client.get.return_value = mock_res

        with patch("app.plugin_framework.builtin_plugins.autogenrss.backend.handlers.zhuque.HttpClient") as mock_http:
            mock_http.return_value = mock_client
            result = handler.generate(self._make_ctx())

        assert result.ok is False
        assert "cookie失效" in result.msg

    def test_missing_csrf(self):
        plugin_ctx = self._make_plugin_ctx()
        handler = ZhuQue(plugin_ctx, None, None)

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.text = "<html><body>hello</body></html>"
        mock_client.get.return_value = mock_res

        with patch("app.plugin_framework.builtin_plugins.autogenrss.backend.handlers.zhuque.HttpClient") as mock_http:
            mock_http.return_value = mock_client
            result = handler.generate(self._make_ctx())

        assert result.ok is False
        assert "CSRF" in result.msg

    def test_rss_link_generated(self):
        plugin_ctx = self._make_plugin_ctx()
        handler = ZhuQue(plugin_ctx, None, None)
        mock_repo = MagicMock()
        handler._site_repo = mock_repo

        home_res = MagicMock()
        home_res.text = '<html><meta name="x-csrf-token" content="token123"></html>'

        security_res = MagicMock()
        security_res.json.return_value = {
            "status": 200,
            "data": {"rssKey": "rss123", "torrentKey": "torrent456"},
        }

        def _get_side_effect(url, **kwargs):
            if "getSecurityInfo" in url:
                return security_res
            return home_res

        mock_client = MagicMock()
        mock_client.get.side_effect = _get_side_effect

        with patch("app.plugin_framework.builtin_plugins.autogenrss.backend.handlers.zhuque.HttpClient") as mock_http:
            mock_http.return_value = mock_client
            result = handler.generate(self._make_ctx())

        assert result.ok is True
        mock_repo.update_site_rssurl.assert_called_once()

    def test_security_info_failure(self):
        plugin_ctx = self._make_plugin_ctx()
        handler = ZhuQue(plugin_ctx, None, None)

        home_res = MagicMock()
        home_res.text = '<html><meta name="x-csrf-token" content="token123"></html>'

        mock_client = MagicMock()
        mock_client.get.side_effect = [home_res, Exception("connection failed")]

        with patch("app.plugin_framework.builtin_plugins.autogenrss.backend.handlers.zhuque.HttpClient") as mock_http:
            mock_http.return_value = mock_client
            result = handler.generate(self._make_ctx())

        assert result.ok is False
        assert "请检查站点连通性" in result.msg

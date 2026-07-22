from unittest.mock import MagicMock, patch

from app.plugin_framework.builtin_plugins.autogenrss.backend.handlers._form import (
    FormRssGenHandler,
)
from app.plugin_framework.builtin_plugins.autogenrss.backend.handlers.base import (
    SiteRssGenContext,
)


class TestFormRssGenHandler:
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
        return FormRssGenHandler(plugin_ctx, None, None, None, config or {})

    def test_no_site_url(self):
        handler = self._make_handler()
        ctx = self._make_ctx(site_url="")
        result = handler.generate(ctx)
        assert result.ok is True

    def test_no_cookie_or_headers(self):
        handler = self._make_handler()
        ctx = self._make_ctx(cookie=None, headers=None)
        result = handler.generate(ctx)
        assert result.ok is False
        assert "未配置" in result.msg

    @patch("app.plugin_framework.builtin_plugins.autogenrss.backend.handlers._form.is_logged_in")
    def test_rss_link_parsed(self, mock_is_logged_in):
        mock_is_logged_in.return_value = True
        handler = self._make_handler()
        ctx = self._make_ctx()

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.text = '<html><a href="/rss.php?key=1&linktype=dl">rss</a></html>'
        mock_client.post.return_value = mock_res

        mock_repo = MagicMock()
        handler._site_repo = mock_repo

        with patch.object(handler, "_http_client", return_value=mock_client):
            result = handler.generate(ctx)

        assert result.ok is True
        assert "生成RSS成功" in result.msg
        mock_repo.update_site_rssurl.assert_called_once()

    def test_cookie_expired(self):
        handler = self._make_handler()
        ctx = self._make_ctx()

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.text = '<html><a href="login.php">登录</a></html>'
        mock_client.post.return_value = mock_res

        with patch.object(handler, "_http_client", return_value=mock_client):
            result = handler.generate(ctx)

        assert result.ok is False
        assert "cookie失效" in result.msg

    @patch("app.plugin_framework.builtin_plugins.autogenrss.backend.handlers._form.under_challenge")
    def test_cloudflare(self, mock_under_challenge):
        mock_under_challenge.return_value = True
        handler = self._make_handler()
        ctx = self._make_ctx()

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.text = '<html><div id="challenge-running">Cloudflare</div></html>'
        mock_client.post.return_value = mock_res

        with patch.object(handler, "_http_client", return_value=mock_client):
            result = handler.generate(ctx)

        assert result.ok is False
        assert "Cloudflare" in result.msg

    def test_site_unreachable(self):
        handler = self._make_handler()
        ctx = self._make_ctx()

        mock_client = MagicMock()
        mock_client.post.side_effect = Exception("connection failed")

        with patch.object(handler, "_http_client", return_value=mock_client):
            result = handler.generate(ctx)

        assert result.ok is False
        assert "请检查站点连通性" in result.msg

    @patch("app.plugin_framework.builtin_plugins.autogenrss.backend.handlers._form.is_logged_in")
    def test_2fa_required(self, mock_is_logged_in):
        mock_is_logged_in.return_value = True
        handler = self._make_handler()
        ctx = self._make_ctx()

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.text = "<html>完成两步验证</html>"
        mock_client.post.return_value = mock_res

        with patch.object(handler, "_http_client", return_value=mock_client):
            result = handler.generate(ctx)

        assert result.ok is False
        assert "需要两步验证" in result.msg

    @patch("app.plugin_framework.builtin_plugins.autogenrss.backend.handlers._form.is_logged_in")
    def test_no_rss_link(self, mock_is_logged_in):
        mock_is_logged_in.return_value = True
        handler = self._make_handler()
        ctx = self._make_ctx()

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.text = "<html>no rss link</html>"
        mock_client.post.return_value = mock_res

        with patch.object(handler, "_http_client", return_value=mock_client):
            result = handler.generate(ctx)

        assert result.ok is False
        assert "未解析到RSS链接" in result.msg

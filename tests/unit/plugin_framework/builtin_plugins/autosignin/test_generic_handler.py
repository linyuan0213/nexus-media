from unittest.mock import MagicMock, patch

from app.plugin_framework.builtin_plugins.autosignin.backend.handlers._generic import (
    GenericSigninHandler,
)
from app.plugin_framework.builtin_plugins.autosignin.backend.handlers.base import (
    SiteSigninContext,
)


class TestGenericSigninHandler:
    def _make_ctx(self, **overrides) -> SiteSigninContext:
        defaults = {
            "site": "test_site",
            "site_url": "https://test.site/sign",
            "cookie": "uid=1;pass=abc",
            "api_key": None,
            "bearer_token": None,
            "ua": "Mozilla/5.0",
            "proxy_url": None,
            "headers": None,
            "is_chrome": False,
            "raw": {},
        }
        defaults.update(overrides)
        return SiteSigninContext(**defaults)

    def test_no_site_url(self):
        handler = GenericSigninHandler(MagicMock(), None)
        ctx = self._make_ctx(site_url="")
        result = handler.signin(ctx)
        assert result.ok is True
        assert result.msg == ""

    def test_success_marker(self):
        handler = GenericSigninHandler(MagicMock(), None, success_markers=["签到成功"])
        ctx = self._make_ctx()

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.text = "<html>签到成功</html>"
        mock_client.get.return_value = mock_res

        with patch.object(handler, "_http_client", return_value=mock_client):
            result = handler.signin(ctx)

        assert result.ok is True
        assert "签到成功" in result.msg

    def test_already_marker(self):
        handler = GenericSigninHandler(MagicMock(), None, already_markers=["今日已签到"])
        ctx = self._make_ctx()

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.text = "<html>今日已签到</html>"
        mock_client.get.return_value = mock_res

        with patch.object(handler, "_http_client", return_value=mock_client):
            result = handler.signin(ctx)

        assert result.ok is True
        assert "已签到" in result.msg

    def test_cookie_expired(self):
        handler = GenericSigninHandler(MagicMock(), None)
        ctx = self._make_ctx()

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.text = '<html><a href="login.php">登录</a></html>'
        mock_client.get.return_value = mock_res

        with patch.object(handler, "_http_client", return_value=mock_client):
            result = handler.signin(ctx)

        assert result.ok is False
        assert "cookie失效" in result.msg

    def test_site_unreachable(self):
        handler = GenericSigninHandler(MagicMock(), None)
        ctx = self._make_ctx()

        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("connection failed")

        with patch.object(handler, "_http_client", return_value=mock_client):
            result = handler.signin(ctx)

        assert result.ok is False
        assert "请检查站点连通性" in result.msg

    def test_no_match(self):
        handler = GenericSigninHandler(MagicMock(), None)
        ctx = self._make_ctx()

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.text = "<html>unknown content</html>"
        mock_client.get.return_value = mock_res

        with patch.object(handler, "_http_client", return_value=mock_client):
            result = handler.signin(ctx)

        assert result.ok is False
        assert "签到接口返回" in result.msg

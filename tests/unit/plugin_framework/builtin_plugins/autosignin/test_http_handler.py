from unittest.mock import MagicMock, patch

from app.plugin_framework.builtin_plugins.autosignin.backend.handlers._http import (
    HttpSigninHandler,
)
from app.plugin_framework.builtin_plugins.autosignin.backend.handlers.base import (
    SiteSigninContext,
)
from app.plugin_framework.builtin_plugins.autosignin.backend.signin_config_store import (
    SigninConfigStore,
)


class TestHttpSigninHandler:
    def _make_ctx(self, **overrides) -> SiteSigninContext:
        defaults = {
            "site": "test_site",
            "site_id": "test",
            "site_url": "https://test.site/sign",
            "cookie": "uid=1;pass=abc",
            "api_key": None,
            "bearer_token": None,
            "ua": "Mozilla/5.0",
            "proxy_url": None,
            "headers": None,
            "is_browser": False,
            "raw": {},
        }
        defaults.update(overrides)
        return SiteSigninContext(**defaults)

    def test_no_site_url(self):
        handler = HttpSigninHandler(MagicMock(), None, {})
        ctx = self._make_ctx(site_url="")
        result = handler.signin(ctx)
        assert result.ok is True
        assert result.msg == ""

    def test_success_marker(self):
        handler = HttpSigninHandler(MagicMock(), None, {"success_markers": ["签到成功"]})
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
        handler = HttpSigninHandler(MagicMock(), None, {"already_markers": ["今日已签到"]})
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
        handler = HttpSigninHandler(MagicMock(), None, {})
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
        handler = HttpSigninHandler(MagicMock(), None, {})
        ctx = self._make_ctx()

        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("connection failed")

        with patch.object(handler, "_http_client", return_value=mock_client):
            result = handler.signin(ctx)

        assert result.ok is False
        assert "请检查站点连通性" in result.msg

    def test_no_match(self):
        handler = HttpSigninHandler(MagicMock(), None, {})
        ctx = self._make_ctx()

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.text = "<html>unknown content</html>"
        mock_client.get.return_value = mock_res

        with patch.object(handler, "_http_client", return_value=mock_client):
            result = handler.signin(ctx)

        assert result.ok is False
        assert "签到接口返回" in result.msg

    def test_success_absent_marker(self):
        handler = HttpSigninHandler(MagicMock(), None, {"success_absent_markers": ["每日签到"]})
        ctx = self._make_ctx()

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.text = "<html>无签到按钮</html>"
        mock_client.get.return_value = mock_res

        with patch.object(handler, "_http_client", return_value=mock_client):
            result = handler.signin(ctx)

        assert result.ok is True
        assert "签到成功" in result.msg

    def test_already_absent_marker(self):
        handler = HttpSigninHandler(MagicMock(), None, {"already_absent_markers": ["每日签到"]})
        ctx = self._make_ctx()

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.text = "<html>无签到按钮</html>"
        mock_client.get.return_value = mock_res

        with patch.object(handler, "_http_client", return_value=mock_client):
            result = handler.signin(ctx)

        assert result.ok is True
        assert "已签到" in result.msg


class TestDiscfanMarkers:
    def _config(self):
        configs = SigninConfigStore(MagicMock()).load_builtin()
        return next(item for item in configs if item["site_id"] == "discfan")

    def _run(self, text: str):
        handler = HttpSigninHandler(MagicMock(), None, self._config())
        ctx = SiteSigninContext(
            site="蝶粉",
            site_id="discfan",
            site_url="https://discfan.net",
            cookie="uid=1",
            api_key=None,
            bearer_token=None,
            ua="",
            proxy_url=None,
            headers=None,
            is_browser=False,
            raw={},
        )
        client = MagicMock()
        response = MagicMock()
        response.text = text
        client.get.return_value = response
        with patch.object(handler, "_http_client", return_value=client):
            return handler.signin(ctx)

    def test_traditional_success(self):
        result = self._run("這是您的第 3 次簽到，已連續簽到 2 天，本次簽到獲得 10 魔力值。")
        assert result.ok is True
        assert "签到成功" in result.msg

    def test_traditional_already(self):
        result = self._run("您今天已經簽到過了，請勿重複刷新。")
        assert result.ok is True
        assert "已签到" in result.msg

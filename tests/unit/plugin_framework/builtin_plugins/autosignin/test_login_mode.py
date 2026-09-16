"""签到插件「登录模式」（仅刷新首页，不签到）测试."""

from unittest.mock import MagicMock, patch

from app.plugin_framework.builtin_plugins.autosignin.backend.handlers._browser import (
    BrowserSigninHandler,
)
from app.plugin_framework.builtin_plugins.autosignin.backend.handlers._http import (
    HttpSigninHandler,
)
from app.plugin_framework.builtin_plugins.autosignin.backend.handlers.base import (
    SigninResult,
    SiteSigninContext,
)
from app.plugin_framework.builtin_plugins.autosignin.backend.registry import HandlerRegistry
from app.plugin_framework.builtin_plugins.autosignin.backend.signer import SigninEngine


def _ctx(**overrides) -> SiteSigninContext:
    defaults = {
        "site": "蝶粉",
        "site_id": "discfan",
        "site_url": "https://discfan.net",
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


def _plugin_ctx():
    ctx = MagicMock()
    ctx.site_engine.get_by_id.return_value = None
    return ctx


class TestHttpLoginMode:
    def test_refreshes_homepage_only(self):
        handler = HttpSigninHandler(_plugin_ctx(), None, {"mode": "login"})
        client = MagicMock()
        res = MagicMock()
        res.text = "<html>欢迎回来</html>"
        client.get.return_value = res

        with (
            patch.object(handler, "_http_client", return_value=client),
            patch(
                "app.plugin_framework.builtin_plugins.autosignin.backend.handlers._http.is_logged_in",
                return_value=True,
            ),
        ):
            result = handler.signin(_ctx())

        assert result.ok is True
        assert "登录态已刷新" in result.msg
        assert client.get.call_args.kwargs["url"].rstrip("/") == "https://discfan.net"

    def test_cookie_expired(self):
        handler = HttpSigninHandler(_plugin_ctx(), None, {"mode": "login"})
        client = MagicMock()
        res = MagicMock()
        res.text = "<html>请登录</html>"
        client.get.return_value = res

        with (
            patch.object(handler, "_http_client", return_value=client),
            patch(
                "app.plugin_framework.builtin_plugins.autosignin.backend.handlers._http.is_logged_in",
                return_value=False,
            ),
        ):
            result = handler.signin(_ctx())

        assert result.ok is False
        assert "cookie失效" in result.msg


class TestBrowserLoginMode:
    def test_refreshes_homepage_without_checkin(self):
        handler = BrowserSigninHandler(_plugin_ctx(), None, {"mode": "login"})
        session = MagicMock()
        session.navigate.return_value = {"html": "<html>首页</html>"}
        session.html.return_value = "<html>首页</html>"

        with (
            patch(
                "app.plugin_framework.builtin_plugins.autosignin.backend.handlers._browser.get_chrome_server_url",
                return_value="http://chrome:9850",
            ),
            patch(
                "app.plugin_framework.builtin_plugins.autosignin.backend.handlers._browser.settings"
            ) as mock_settings,
            patch(
                "app.plugin_framework.builtin_plugins.autosignin.backend.handlers._browser.BrowserSession"
            ) as mock_session,
            patch(
                "app.plugin_framework.builtin_plugins.autosignin.backend.handlers._browser.wait_challenge_clear",
                side_effect=lambda _session, html, timeout=180: html,
            ),
            patch(
                "app.plugin_framework.builtin_plugins.autosignin.backend.handlers._browser.has_pending_turnstile",
                return_value=False,
            ),
            patch(
                "app.plugin_framework.builtin_plugins.autosignin.backend.handlers._browser.is_logged_in",
                return_value=True,
            ),
        ):
            mock_settings.get.return_value = {}
            mock_session.return_value.__enter__.return_value = session
            result = handler.signin(_ctx(is_browser=True))

        assert result.ok is True
        assert "登录态已刷新" in result.msg
        assert session.navigate.call_args.args[0] == "https://discfan.net"
        session.click.assert_not_called()

    def test_not_logged_in(self):
        handler = BrowserSigninHandler(_plugin_ctx(), None, {"mode": "login"})
        session = MagicMock()
        session.navigate.return_value = {"html": "<html>请登录</html>"}

        with (
            patch(
                "app.plugin_framework.builtin_plugins.autosignin.backend.handlers._browser.get_chrome_server_url",
                return_value="http://chrome:9850",
            ),
            patch(
                "app.plugin_framework.builtin_plugins.autosignin.backend.handlers._browser.settings"
            ) as mock_settings,
            patch(
                "app.plugin_framework.builtin_plugins.autosignin.backend.handlers._browser.BrowserSession"
            ) as mock_session,
            patch(
                "app.plugin_framework.builtin_plugins.autosignin.backend.handlers._browser.wait_challenge_clear",
                side_effect=lambda _session, html, timeout=180: html,
            ),
            patch(
                "app.plugin_framework.builtin_plugins.autosignin.backend.handlers._browser.has_pending_turnstile",
                return_value=False,
            ),
            patch(
                "app.plugin_framework.builtin_plugins.autosignin.backend.handlers._browser.is_logged_in",
                return_value=False,
            ),
        ):
            mock_settings.get.return_value = {}
            mock_session.return_value.__enter__.return_value = session
            result = handler.signin(_ctx(is_browser=True))

        assert result.ok is False
        assert "cookie失效" in result.msg


class TestRegistryLoginFactories:
    def _registry(self):
        ctx = _plugin_ctx()
        return HandlerRegistry(ctx, MagicMock(), ctx.site_engine, [])

    def test_get_login_is_http_login_mode(self):
        handler = self._registry().get_login()()
        assert isinstance(handler, HttpSigninHandler)
        assert handler._config == {"mode": "login"}

    def test_get_login_browser_is_browser_login_mode(self):
        handler = self._registry().get_login_browser()()
        assert isinstance(handler, BrowserSigninHandler)
        assert handler._config == {"mode": "login"}


class TestSignerLoginDispatch:
    @staticmethod
    def _engine(registry=None, cache=None):
        engine = SigninEngine(MagicMock(), registry or MagicMock(), site_cache=cache or MagicMock(), site_engine=None)
        setattr(engine, "_registry", registry or MagicMock())
        setattr(engine, "_site_cache", cache or MagicMock())
        return engine

    def test_login_site_uses_login_handler_and_bypasses_dedicated(self):
        registry = MagicMock()
        dedicated_handler = MagicMock()
        dedicated_handler.signin.return_value = SigninResult.success("蝶粉")
        registry.get.return_value = lambda: dedicated_handler
        login_handler = MagicMock()
        login_handler.signin.return_value = SigninResult.login_refresh("蝶粉")
        registry.get_login.return_value = lambda: login_handler
        engine = self._engine(registry=registry)
        engine._registry = registry

        msg = engine._signin_site(
            {
                "id": "discfan",
                "name": "蝶粉",
                "signurl": "https://discfan.net",
                "cookie": "a=1",
                "signin_mode": "login",
            }
        )

        assert "登录态已刷新" in msg
        login_handler.signin.assert_called_once()
        dedicated_handler.signin.assert_not_called()

    def test_login_browser_site_uses_browser_login_handler(self):
        registry = MagicMock()
        registry.get.return_value = None
        login_browser_handler = MagicMock()
        login_browser_handler.signin.return_value = SigninResult.login_refresh("蝶粉")
        registry.get_login_browser.return_value = lambda: login_browser_handler
        engine = self._engine(registry=registry)
        engine._registry = registry

        msg = engine._signin_site(
            {
                "id": "discfan",
                "name": "蝶粉",
                "signurl": "https://discfan.net",
                "cookie": "a=1",
                "signin_mode": "login",
                "is_browser": True,
            }
        )

        assert "登录态已刷新" in msg
        login_browser_handler.signin.assert_called_once()
        engine._registry.get_login.assert_not_called()

    def test_login_refresh_not_recorded_as_signed(self):
        ctx = MagicMock()
        cache = MagicMock()
        cache.get_site_dict.return_value = [{"name": "蝶粉", "id": 42}]
        engine = self._engine(cache=cache)
        engine.ctx = ctx
        history: dict = {}

        def get_history(key=None):
            return history.get(key)

        def update_history(key, value):
            history[key] = value

        engine._process_results(
            ["[蝶粉]登录态已刷新"],
            sign_sites_cfg=[],
            special_sites=[],
            retry_keyword=None,
            notify=True,
            today_str="2026-09-15",
            get_history=get_history,
            update_history=update_history,
        )

        assert history["2026-09-15"]["sign"] == []
        assert history["2026-09-15"]["retry"] == []
        ctx._message.send_site_signin_message.assert_called_once()
        assert "[蝶粉]登录态已刷新" in ctx._message.send_site_signin_message.call_args.args[0]

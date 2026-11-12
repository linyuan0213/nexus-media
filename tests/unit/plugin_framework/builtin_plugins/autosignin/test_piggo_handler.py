"""Piggo 浏览器签到回归测试."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.plugin_framework.builtin_plugins.autosignin.backend.handlers import piggo
from app.plugin_framework.builtin_plugins.autosignin.backend.handlers.base import SiteSigninContext


class _FakeBrowserSession:
    init_kwargs: dict = {}
    navigations: list = []

    def __init__(self, **kwargs):
        type(self).init_kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def navigate(self, url, **kwargs):
        type(self).navigations.append((url, kwargs))
        return {}

    def execute(self, script):
        return ""

    def current_page(self):
        return {"url": ""}

    def turnstile(self, _timeout):
        return {"solved": False}


def test_piggo_cookie_passed_to_navigate_not_constructor(monkeypatch):
    monkeypatch.setattr(piggo, "BrowserSession", _FakeBrowserSession)
    monkeypatch.setattr(piggo, "get_chrome_server_url", lambda: "http://chrome:9850")
    monkeypatch.setattr(
        piggo,
        "resolve_spa_credentials",
        lambda *_args, **_kwargs: SimpleNamespace(bearer_token="token", cookie="uid=1"),
    )
    ctx = SiteSigninContext(
        site="猪猪",
        site_id="piggo",
        site_url="https://piggo.me",
        cookie="site-cookie",
        api_key=None,
        bearer_token=None,
        ua=None,
        proxy_url=None,
        raw={},
    )
    plugin_ctx = MagicMock()
    plugin_ctx.site_engine.get_by_id.return_value = object()
    piggo.Piggo(plugin_ctx, None).signin(ctx)

    assert "cookie" not in _FakeBrowserSession.init_kwargs
    assert _FakeBrowserSession.navigations[0][1]["cookie"] == "uid=1"

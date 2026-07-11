"""Browser transport and browser mode 配置单元测试。"""

from app.infrastructure.http.browser_transport import _make_session_key
from app.infrastructure.http.config import BrowserModeConfig, HttpClientConfig


class TestMakeSessionKey:
    def test_render_html_does_not_change_session_key(self):
        browser_false = BrowserModeConfig(
            enabled=True,
            site_key="site",
            render_html=False,
        )
        browser_true = BrowserModeConfig(
            enabled=True,
            site_key="site",
            render_html=True,
        )
        assert _make_session_key("site", browser_false) == _make_session_key("site", browser_true)

    def test_different_fingerprint_changes_session_key(self):
        browser_a = BrowserModeConfig(enabled=True, site_key="site", fingerprint_profile="stealth")
        browser_b = BrowserModeConfig(enabled=True, site_key="site", fingerprint_profile="paranoid")
        assert _make_session_key("site", browser_a) != _make_session_key("site", browser_b)


class TestBrowserModeConfig:
    def test_browser_fetch_on_challenge_default_true(self):
        cfg = BrowserModeConfig()
        assert cfg.browser_fetch_on_challenge is True

    def test_navigate_timeout_default(self):
        cfg = BrowserModeConfig()
        assert cfg.navigate_timeout == 90


class TestHttpClientConfig:
    def test_timeout_default(self):
        cfg = HttpClientConfig()
        assert cfg.timeout == 120.0

"""config_tools 单元测试"""

from unittest.mock import MagicMock

import pytest

from app.core.constants import DEFAULT_UA, TMDB_API_DOMAINS
from app.utils import config_tools


class TestConfigTools:
    @pytest.fixture(autouse=True)
    def reset_favtype(self):
        config_tools.RMT_FAVTYPE = ""

    def _mock_settings(self, monkeypatch, app_config):
        mock = MagicMock()
        mock.get.side_effect = lambda node=None: {"app": app_config} if node is None else app_config
        monkeypatch.setattr(config_tools, "settings", mock)

    def test_get_proxies(self, monkeypatch):
        proxies = {"http": "http://proxy:1080", "https": "http://proxy:1080"}
        self._mock_settings(monkeypatch, {"proxies": proxies})

        assert config_tools.get_proxies() == proxies

    def test_get_ua_custom(self, monkeypatch):
        self._mock_settings(monkeypatch, {"user_agent": "custom-ua"})

        assert config_tools.get_ua() == "custom-ua"

    def test_get_ua_default(self, monkeypatch):
        self._mock_settings(monkeypatch, {"user_agent": None})

        assert config_tools.get_ua() == DEFAULT_UA

    def test_get_domain_adds_scheme_and_removes_trailing_slash(self, monkeypatch):
        self._mock_settings(monkeypatch, {"domain": "example.com/"})

        assert config_tools.get_domain() == "http://example.com"

    def test_get_domain_none(self, monkeypatch):
        self._mock_settings(monkeypatch, {"domain": None})

        assert config_tools.get_domain() is None

    def test_get_tmdbapi_url_default(self, monkeypatch):
        self._mock_settings(monkeypatch, {"tmdb_domain": None})

        assert config_tools.get_tmdbapi_url() == f"https://{TMDB_API_DOMAINS[0]}/3"

    def test_get_tmdbapi_url_custom(self, monkeypatch):
        self._mock_settings(monkeypatch, {"tmdb_domain": "tmdb.custom.com"})

        assert config_tools.get_tmdbapi_url() == "https://tmdb.custom.com/3"

    def test_update_favtype(self):
        config_tools.update_favtype("电影")
        assert config_tools.RMT_FAVTYPE == "电影"

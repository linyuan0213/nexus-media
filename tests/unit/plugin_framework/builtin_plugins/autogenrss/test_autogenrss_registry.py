from unittest.mock import MagicMock, patch

from app.plugin_framework.builtin_plugins.autogenrss.backend.registry import (
    RssHandlerRegistry,
)


class TestRssHandlerRegistry:
    def _make_reg(self, rss_configs=None, plugin_ctx=None):
        plugin_ctx = plugin_ctx or MagicMock()
        plugin_ctx.site_engine = MagicMock()
        return RssHandlerRegistry(
            plugin_ctx,
            MagicMock(),
            plugin_ctx.site_engine,
            rss_configs or [],
        )

    def test_len(self):
        reg = self._make_reg()
        reg._handlers = {"a": MagicMock(), "b": MagicMock()}
        assert len(reg) == 2

    def test_get_by_site_id(self):
        factory = MagicMock()
        reg = self._make_reg()
        reg._handlers = {"test": factory}
        result = reg.get("test")
        assert result is factory

    def test_get_unknown_site_id(self):
        reg = self._make_reg()
        reg._handlers = {"test": MagicMock()}
        result = reg.get("unknown")
        assert result is None

    def test_get_empty(self):
        reg = self._make_reg()
        reg._handlers = {"test": MagicMock()}
        assert reg.get("") is None
        assert reg.get(None) is None

    @patch("app.plugin_framework.builtin_plugins.autogenrss.backend.registry.SubmoduleLoader")
    def test_load_custom_handler(self, mock_loader):
        mock_handler = MagicMock(site_id="test")
        mock_loader.import_submodules.return_value = [mock_handler]

        reg = self._make_reg()
        reg.load()
        assert "test" in reg._handlers
        assert reg._handlers["test"] is not None

    @patch("app.plugin_framework.builtin_plugins.autogenrss.backend.registry.SubmoduleLoader")
    def test_generic_handlers_not_loaded(self, mock_loader):
        class FormHandler:
            site_id = "__form__"

        class ApiHandler:
            site_id = "__api__"

        class BrowserHandler:
            site_id = "__browser__"

        class HDHomeHandler:
            site_id = "hdhome"

        all_handlers = [FormHandler, ApiHandler, BrowserHandler, HDHomeHandler]

        def _apply_filter(package, filter_func):
            return [h for h in all_handlers if filter_func(h.__name__, h)]

        mock_loader.import_submodules.side_effect = _apply_filter

        reg = self._make_reg()
        reg.load()
        assert "hdhome" in reg._handlers
        assert "__form__" not in reg._handlers
        assert "__api__" not in reg._handlers
        assert "__browser__" not in reg._handlers

    def test_load_declarative_handlers(self):
        configs = [
            {"site_id": "api_site", "type": "api"},
            {"site_id": "browser_site", "type": "browser"},
            {"site_id": "form_site", "type": "form"},
        ]
        reg = self._make_reg(rss_configs=configs)
        reg.load()
        assert "api_site" in reg._handlers
        assert "browser_site" in reg._handlers
        assert "form_site" in reg._handlers

    def test_fallback(self):
        reg = self._make_reg(rss_configs=[{"site_id": "__fallback_form__", "type": "form"}])
        reg.load()
        factory = reg.get_fallback("unknown")
        assert factory is not None
        handler = factory()
        assert handler is not None

    def test_generic(self):
        reg = self._make_reg()
        reg.load()
        factory = reg.get_generic()
        assert factory is not None
        handler = factory()
        assert handler is not None

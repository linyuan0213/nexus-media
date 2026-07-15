from unittest.mock import MagicMock, patch

from app.plugin_framework.builtin_plugins.autosignin.backend.registry import HandlerRegistry


class TestHandlerRegistry:
    def _make_reg(self, signin_configs=None, plugin_ctx=None):
        plugin_ctx = plugin_ctx or MagicMock()
        plugin_ctx.site_engine = MagicMock()
        return HandlerRegistry(
            plugin_ctx,
            MagicMock(),
            plugin_ctx.site_engine,
            signin_configs or [],
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

    @patch("app.plugin_framework.builtin_plugins.autosignin.backend.registry.SubmoduleLoader")
    def test_load_custom_handler(self, mock_loader):
        mock_handler = MagicMock(site_id="test")
        mock_loader.import_submodules.return_value = [mock_handler]

        reg = self._make_reg()
        reg.load()
        assert "test" in reg._handlers
        assert reg._handlers["test"] is not None

    def test_load_generic_handlers(self):
        configs = [
            {"site_id": "api_site", "type": "api"},
            {"site_id": "browser_site", "type": "browser"},
            {"site_id": "http_site", "type": "http"},
        ]
        reg = self._make_reg(signin_configs=configs)
        reg.load()
        assert "api_site" in reg._handlers
        assert "browser_site" in reg._handlers
        assert "http_site" in reg._handlers

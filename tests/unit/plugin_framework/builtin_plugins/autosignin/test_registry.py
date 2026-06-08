from unittest.mock import MagicMock, patch

from app.plugin_framework.builtin_plugins.autosignin.backend.registry import HandlerRegistry


class TestHandlerRegistry:
    def test_len(self):
        reg = HandlerRegistry(MagicMock(), MagicMock(), [])
        reg._handlers = {"a.com": MagicMock(), "b.com": MagicMock()}
        assert len(reg) == 2

    def test_get_by_domain(self):
        factory = MagicMock()
        reg = HandlerRegistry(MagicMock(), MagicMock(), [])
        reg._handlers = {"52pt.site": factory}
        result = reg.get("https://52pt.site/bakatest.php")
        assert result is factory

    def test_get_unknown_domain(self):
        reg = HandlerRegistry(MagicMock(), MagicMock(), [])
        reg._handlers = {"52pt.site": MagicMock()}
        result = reg.get("https://unknown.site/sign")
        assert result is None

    def test_get_empty_signurl(self):
        reg = HandlerRegistry(MagicMock(), MagicMock(), [])
        reg._handlers = {"52pt.site": MagicMock()}
        assert reg.get("") is None
        assert reg.get(None) is None

    @patch("app.plugin_framework.builtin_plugins.autosignin.backend.registry.SubmoduleLoader")
    def test_load(self, mock_loader):
        mock_handler = MagicMock(site_url="52pt.site")
        mock_loader.import_submodules.return_value = [mock_handler]

        reg = HandlerRegistry(MagicMock(), MagicMock(), [])
        reg.load()
        assert "52pt.site" in reg._handlers
        assert reg._handlers["52pt.site"] is not None

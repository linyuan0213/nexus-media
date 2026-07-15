from unittest.mock import MagicMock, patch

from app.plugin_framework.builtin_plugins.autosignin.backend.signin_config_store import (
    SigninConfigStore,
)


class TestSigninConfigStore:
    def _make_store(self, plugin_ctx=None, site_engine=None):
        return SigninConfigStore(plugin_ctx or MagicMock(), site_engine)

    @patch("app.plugin_framework.builtin_plugins.autosignin.backend.signin_config_store.os.path.isdir")
    @patch("builtins.open")
    @patch("app.plugin_framework.builtin_plugins.autosignin.backend.signin_config_store.os.listdir")
    def test_load_builtin(self, mock_listdir, mock_open, mock_isdir):
        mock_isdir.return_value = True
        mock_listdir.return_value = ["test.json"]
        mock_open.return_value.__enter__.return_value.read.return_value = '{"site_id": "test"}'

        store = self._make_store()
        result = store.load_builtin()

        assert len(result) == 1
        assert result[0]["site_id"] == "test"

    def test_user_overrides_builtin(self):
        plugin_ctx = MagicMock()
        plugin_ctx.read_data.return_value = '[{"site_id": "test", "custom": true}]'

        store = self._make_store(plugin_ctx)
        with patch.object(store, "load_builtin", return_value=[{"site_id": "test"}]):
            result = store.load()

        assert len(result) == 1
        assert result[0].get("custom") is True

    def test_invalid_user_config_uses_builtin(self):
        plugin_ctx = MagicMock()
        plugin_ctx.read_data.return_value = "not valid json"

        store = self._make_store(plugin_ctx)
        with patch.object(store, "load_builtin", return_value=[{"site_id": "test"}]):
            result = store.load()

        assert len(result) == 1
        assert result[0]["site_id"] == "test"

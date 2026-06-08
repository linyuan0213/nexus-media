from unittest.mock import MagicMock, patch

from app.plugin_framework.builtin_plugins.autosignin.backend.credentials import (
    CredentialResolver,
    HeaderSource,
    LocalStorageSource,
)


class TestHeaderSource:
    def test_extract_found(self):
        source = HeaderSource("x-sign-token")
        assert source.extract({"headers": {"x-sign-token": "abc123"}}) == "abc123"

    def test_extract_with_prefix(self):
        source = HeaderSource("authorization", strip_prefix="Bearer ")
        assert source.extract({"headers": {"authorization": "Bearer abc123"}}) == "abc123"

    def test_extract_not_found(self):
        source = HeaderSource("x-missing")
        assert source.extract({"headers": {"x-other": "val"}}) is None

    def test_extract_from_json_string(self):
        source = HeaderSource("x-sign-token")
        assert source.extract({"headers": '{"x-sign-token": "json_val"}'}) == "json_val"


class TestLocalStorageSource:
    @patch("app.plugin_framework.builtin_plugins.autosignin.backend.credentials.CookiecloudAdapter")
    def test_extract_found(self, mock_adapter_cls):
        mock_adapter = MagicMock()
        mock_adapter.get_local_storage.return_value = {"token": "ls_val"}
        mock_adapter_cls.return_value = mock_adapter

        source = LocalStorageSource("rousi.pro", "token")
        assert source.extract({}) == "ls_val"

    @patch("app.plugin_framework.builtin_plugins.autosignin.backend.credentials.CookiecloudAdapter")
    def test_extract_missing(self, mock_adapter_cls):
        mock_adapter = MagicMock()
        mock_adapter.get_local_storage.return_value = None
        mock_adapter_cls.return_value = mock_adapter

        source = LocalStorageSource("rousi.pro", "token")
        assert source.extract({}) is None


class TestCredentialResolver:
    def test_resolve_none_source(self):
        resolver = CredentialResolver({"cookie": "test_cookie"})
        val, need_sync = resolver.resolve(None)
        assert val is None
        assert need_sync is False

    def test_resolve_header_source(self):
        resolver = CredentialResolver({"headers": {"x-sign-token": "tok"}})
        val, need_sync = resolver.resolve({"type": "header", "name": "x-sign-token"})
        assert val == "tok"
        assert need_sync is False

    def test_resolve_local_storage_needs_sync(self):
        resolver = CredentialResolver({})
        val, need_sync = resolver.resolve({"type": "local_storage", "domain": "d", "key": "k"})
        assert val is None
        assert need_sync is True

    def test_resolve_unknown_type_raises(self):
        resolver = CredentialResolver({})
        try:
            resolver.resolve({"type": "unknown"})
            assert False, "Expected ValueError"
        except ValueError as e:
            assert "Unknown credential source type" in str(e)

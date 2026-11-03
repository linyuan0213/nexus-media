"""验证 manifest indexer_providers 会由插件 Sandbox 自动注册。"""

from types import SimpleNamespace
from unittest.mock import Mock

from app.indexer.contract.http import HttpIndexerProvider
from app.plugin_framework.sandbox import PluginSandbox
from app.schemas.plugin import PluginManifest


def test_http_indexer_plugin_is_registered_from_manifest():
    manifest = PluginManifest.from_dict(
        {
            "id": "http_indexer",
            "name": "HTTP Indexer",
            "version": "1.0.0",
            "backend": {
                "entry": "backend.plugin:HttpIndexerPlugin",
                "metadata": {"indexer_providers": [{"key": "http-indexer", "type": "http"}]},
            },
            "frontend": {
                "settings": {
                    "fields": [
                        {"key": "base_url", "type": "text", "required": True},
                        {"key": "token", "type": "password"},
                    ]
                }
            },
        }
    )
    ctx = SimpleNamespace(
        get_config=Mock(return_value={"base_url": "http://127.0.0.1:9000", "token": "x"}),
        register_indexer_provider=Mock(),
        register_metadata_provider=Mock(),
        register_discovery_provider=Mock(),
        register_metadata_profile=Mock(),
    )
    sandbox = object.__new__(PluginSandbox)
    sandbox._load_manifest_metadata(ctx, "http_indexer", "/tmp", manifest)

    ctx.register_indexer_provider.assert_called_once()
    key, provider = ctx.register_indexer_provider.call_args.args
    assert key == "http-indexer"
    assert isinstance(provider, HttpIndexerProvider)
    assert provider.base_url == "http://127.0.0.1:9000"
    provider.close()

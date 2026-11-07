"""manifest backend.metadata 自动注册测试."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.media.metadata import ProviderDescriptor
from app.media.metadata.registry import registry as metadata_registry
from app.plugin_framework.context import PluginContext
from app.plugin_framework.sandbox import PluginSandbox
from app.schemas.plugin import PluginMetadataConfig


def test_manifest_metadata_is_auto_loaded(tmp_path):
    module_name = "demo_metadata_provider"
    (tmp_path / f"{module_name}.py").write_text(
        """
from app.media.metadata import ProviderDescriptor

class DemoProvider:
    descriptor = ProviderDescriptor(provider_key="autoload-demo", display_name="Demo")
""",
        encoding="utf-8",
    )

    metadata = PluginMetadataConfig.from_dict(
        {"providers": [{"key": "autoload-demo", "entry": f"{module_name}:DemoProvider"}]}
    )
    ctx = PluginContext("autoload-plugin", message=MagicMock(), manifest_metadata=metadata)
    sandbox = PluginSandbox.__new__(PluginSandbox)

    try:
        manifest = SimpleNamespace(backend=SimpleNamespace(metadata=metadata))
        sandbox._load_manifest_metadata(ctx, "autoload-plugin", str(tmp_path), manifest)
        provider = metadata_registry.get_provider("autoload-demo")
        assert provider is not None
        assert isinstance(provider.descriptor, ProviderDescriptor)
    finally:
        ctx.unregister_all_metadata()
        sys.modules.pop(module_name, None)


def test_manifest_media_type_descriptor_is_auto_loaded(tmp_path):
    metadata = PluginMetadataConfig.from_dict(
        {
            "media_types": [
                {
                    "key": "plugin:autoload-plugin:demo",
                    "kind": "episodic",
                    "display_name": "Demo Type",
                    "code_identity": True,
                    "content_profiles": ["demo_profile"],
                }
            ]
        }
    )
    ctx = PluginContext("autoload-plugin", message=MagicMock(), manifest_metadata=metadata)
    sandbox = PluginSandbox.__new__(PluginSandbox)
    try:
        manifest = SimpleNamespace(backend=SimpleNamespace(metadata=metadata))
        sandbox._load_manifest_metadata(ctx, "autoload-plugin", str(tmp_path), manifest)
        from app.domain.media_types import MediaKind, media_type_registry

        resolved = media_type_registry.resolve("plugin:autoload-plugin:demo", "demo_profile")
        assert resolved.kind == MediaKind.EPISODIC
        assert resolved.code_identity is True
    finally:
        from app.domain.media_types import media_type_registry

        media_type_registry.unregister_namespace("autoload-plugin")

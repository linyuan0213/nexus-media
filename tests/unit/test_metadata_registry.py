"""MetadataRegistry 单元测试."""

import pytest

from app.domain.media_types import MediaKind, ProviderMediaType
from app.media.metadata import (
    ProviderCapability,
    ProviderDescriptor,
    ProviderRef,
    SearchHit,
)
from app.media.metadata.registry import BUILTIN_PLUGIN_ID, MetadataRegistry


class _DummyProvider:
    def __init__(self, key: str, capabilities: set[ProviderCapability], **kwargs) -> None:
        self.descriptor = ProviderDescriptor(
            provider_key=key,
            display_name=key,
            capabilities=frozenset(capabilities),
            provider_media_types=frozenset({ProviderMediaType.MOVIE, ProviderMediaType.SERIES}),
            media_kinds=frozenset({MediaKind.MOVIE, MediaKind.EPISODIC}),
            **kwargs,
        )

    def search(self, query, ctx):
        ref = ProviderRef(provider="x", external_id="1")
        return [SearchHit(provider=self.descriptor.provider_key, ref=ref, title="x")]


def test_register_and_list_by_capability():
    reg = MetadataRegistry()
    tmdb = _DummyProvider("tmdb", {ProviderCapability.DETAIL, ProviderCapability.SEASONS})
    douban = _DummyProvider("douban", {ProviderCapability.DETAIL})
    reg.register_provider(tmdb)
    reg.register_provider(douban)

    assert reg.get_provider("tmdb") is tmdb
    assert [p.descriptor.provider_key for p in reg.list_providers(capability="seasons")] == ["tmdb"]
    assert len(reg.list_providers(capability=ProviderCapability.DETAIL)) == 2


def test_builtin_key_cannot_be_overridden_by_plugin():
    reg = MetadataRegistry()
    reg.register_provider(_DummyProvider("tmdb", {ProviderCapability.DETAIL}))
    with pytest.raises(ValueError, match="内置 key"):
        reg.register_provider(
            _DummyProvider("tmdb", {ProviderCapability.DETAIL}),
            plugin_id="some-plugin",
        )


def test_plugin_can_replace_own_provider():
    reg = MetadataRegistry()
    first = _DummyProvider("x", {ProviderCapability.DETAIL})
    second = _DummyProvider("x", {ProviderCapability.IMAGES})
    reg.register_provider(first, plugin_id="p1")
    reg.register_provider(second, plugin_id="p1")
    assert reg.get_provider("x") is second


def test_declared_key_mismatch_rejected():
    reg = MetadataRegistry()
    with pytest.raises(ValueError, match="不一致"):
        reg.register_provider(
            _DummyProvider("x", {ProviderCapability.DETAIL}),
            plugin_id="p1",
            declared_key="y",
        )


def test_unregister_plugin_removes_all_kinds():
    reg = MetadataRegistry()
    provider = _DummyProvider("x", {ProviderCapability.DETAIL})
    discovery = _DummyProvider("x", {ProviderCapability.DISCOVERY})
    reg.register_provider(provider, plugin_id="p1")
    reg.register_discovery_provider(discovery, plugin_id="p1")
    reg.register_profile("naming", "x", object(), plugin_id="p1")

    reg.unregister_plugin("p1")

    assert reg.get_provider("x") is None
    assert reg.get_discovery_provider("x") is None
    assert reg.get_profile("naming", "x") is None


def test_unregister_wrong_plugin_rejected():
    reg = MetadataRegistry()
    reg.register_provider(_DummyProvider("x", {ProviderCapability.DETAIL}), plugin_id="p1")
    with pytest.raises(ValueError, match="无权"):
        reg.unregister_provider("x", plugin_id="p2")


def test_list_visibility_and_content_profile_filter():
    reg = MetadataRegistry()
    reg.register_provider(
        _DummyProvider(
            "private",
            {ProviderCapability.DETAIL},
            visibility="private",
            content_profiles=frozenset({"music"}),
        )
    )
    reg.register_provider(_DummyProvider("public", {ProviderCapability.DETAIL}, content_profiles=frozenset({"movie"})))

    assert [p.descriptor.provider_key for p in reg.list_providers(visibility="private")] == ["private"]
    assert [p.descriptor.provider_key for p in reg.list_providers(content_profile="music")] == ["private"]


def test_builtin_plugin_constant():
    assert BUILTIN_PLUGIN_ID == "builtin"

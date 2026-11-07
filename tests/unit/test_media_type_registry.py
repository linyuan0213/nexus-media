"""媒体类型注册表测试."""

import pytest

from app.domain.media_types import MediaKind, MediaTypeDescriptor, MediaTypeRegistry
from app.domain.mediatypes import MediaType


def test_core_types_keep_anime_episodic():
    registry = MediaTypeRegistry()
    assert registry.resolve(MediaType.ANIME).kind == MediaKind.EPISODIC
    assert registry.resolve("动漫").key == "anime"
    assert registry.resolve("movie").kind == MediaKind.MOVIE


def test_unknown_is_not_movie():
    registry = MediaTypeRegistry()
    resolved = registry.resolve("plugin:missing:type")
    assert resolved.kind == MediaKind.UNKNOWN
    assert resolved.key == "unknown"


def test_plugin_descriptor_requires_namespace_and_unregisters():
    registry = MediaTypeRegistry()
    descriptor = MediaTypeDescriptor(
        key="plugin:demo:code",
        kind=MediaKind.MOVIE,
        display_name="Demo Code",
        code_identity=True,
        content_profiles=("demo",),
    )
    registry.register(descriptor)
    resolved = registry.resolve("plugin:demo:code", "demo")
    assert resolved.kind == MediaKind.MOVIE
    assert resolved.code_identity is True
    registry.unregister_namespace("demo")
    assert registry.resolve("plugin:demo:code").kind == MediaKind.UNKNOWN


def test_plugin_descriptor_cannot_use_core_key():
    registry = MediaTypeRegistry()
    with pytest.raises(ValueError):
        registry.register(MediaTypeDescriptor("movie", MediaKind.MOVIE, "x"))

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


def test_resolve_profile_uses_plugin_descriptor():
    registry = MediaTypeRegistry()
    registry.register(
        MediaTypeDescriptor(
            key="plugin:demo:profile",
            kind=MediaKind.MOVIE,
            display_name="Plugin Profile",
            content_profiles=("demo_profile",),
        )
    )
    resolved = registry.resolve_profile("demo_profile")
    assert resolved is not None
    assert resolved.key == "plugin:demo:profile"
    assert resolved.kind == MediaKind.MOVIE
    assert registry.resolve_profile("missing_profile") is None


def test_from_payload_supports_old_and_new_queue_shapes():
    registry = MediaTypeRegistry()
    old = registry.from_payload({"media_type": "anime", "content_profile": "anime"})
    assert old.key == "anime"
    assert old.kind == MediaKind.EPISODIC

    registry.register(
        MediaTypeDescriptor(
            key="plugin:demo:queued",
            kind=MediaKind.MOVIE,
            display_name="Queued",
            content_profiles=("demo_q",),
        )
    )
    new = registry.from_payload(
        {
            "media_type_key": "plugin:demo:queued",
            "media_kind": "movie",
            "content_profile": "demo_q",
        }
    )
    assert new.key == "plugin:demo:queued"
    assert new.kind == MediaKind.MOVIE
    registry.unregister_namespace("demo")


def test_provider_contracts_fill_media_kind():
    from app.domain.media_ref import MediaRef
    from app.domain.mediatypes import MediaType
    from app.media.metadata.models import ProviderRecord, ProviderRef

    assert MediaRef("tmdb", "1", media_type=MediaType.MOVIE).media_kind == MediaKind.MOVIE
    ref = ProviderRef(provider="tmdb", external_id="1", media_type=MediaType.ANIME)
    assert ref.media_kind == MediaKind.EPISODIC
    record = ProviderRecord(provider="tmdb", external_id="1", media_type=MediaType.TV)
    assert record.media_kind == MediaKind.EPISODIC


def test_provider_media_type_is_separate_from_internal_type():
    from app.domain.media_ref import MediaRef
    from app.domain.media_types import ProviderMediaType
    from app.media.metadata.models import ProviderRef

    ref = ProviderRef(
        provider="emby",
        external_id="1",
        provider_media_type=ProviderMediaType.SERIES,
    )
    assert ref.provider_media_type == ProviderMediaType.SERIES
    assert ref.media_type == MediaType.TV
    assert ref.media_kind == MediaKind.EPISODIC

    media_ref = MediaRef("emby", "1", provider_media_type=ProviderMediaType.MOVIE)
    assert media_ref.provider_media_type == ProviderMediaType.MOVIE
    assert media_ref.media_kind == MediaKind.MOVIE

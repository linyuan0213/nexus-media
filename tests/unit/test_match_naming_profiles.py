"""MatchChain 与 NamingProfile 扩展测试."""

from typing import Any, cast

from app.domain.media_types import ProviderMediaType
from app.media.metadata.matching import MatchChain
from app.media.metadata.models import Detection
from app.media.metadata.naming import (
    NamingField,
    NamingProfile,
    naming_field_catalog,
    naming_field_keys,
    register_naming_profile,
)
from app.media.metadata.registry import MetadataRegistry
from app.services.transfer.name_format import validate


class _HighPriorityProfile:
    key = "custom"
    content_profile = "custom"
    base_media_type = ProviderMediaType.MOVIE
    priority = 100

    def detect(self, ctx):
        return Detection(content_profile="custom", confidence=0.99, base_media_type=ProviderMediaType.MOVIE)

    def match(self, parsed, ctx):
        return None


class _LowPriorityProfile:
    key = "low"
    content_profile = "low"
    base_media_type = ProviderMediaType.MOVIE
    priority = 50

    def detect(self, ctx):
        return Detection(content_profile="low", confidence=0.2, base_media_type=ProviderMediaType.MOVIE)

    def match(self, parsed, ctx):
        return None


def test_match_chain_prefers_high_priority_profile():
    registry = MetadataRegistry()
    registry.register_profile("match", "custom", _HighPriorityProfile())
    registry.register_profile("match", "low", _LowPriorityProfile())

    detection = MatchChain(registry=registry).detect(cast(Any, object()))

    assert detection is not None
    assert detection.content_profile == "custom"
    assert detection.confidence == 0.99


def test_match_chain_falls_back_to_legacy_when_low_confidence():
    registry = MetadataRegistry()
    registry.register_profile("match", "low", _LowPriorityProfile())

    class _Ctx:
        season = None
        episode = None
        year = "2024"
        source = None
        cn_name = None
        release_group = None
        jp_title = None
        en_name = None
        elements = []

        def has(self, key):
            return False

    detection = MatchChain(registry=registry).detect(cast(Any, _Ctx()))

    assert detection is None


def test_unified_parser_uses_high_confidence_match_profile():
    from app.media.parser.unified import UnifiedParser

    registry = MetadataRegistry()
    registry.register_profile("match", "custom", _HighPriorityProfile())

    result = UnifiedParser(match_chain=MatchChain(registry=registry)).parse("Some.Movie.2024.1080p")

    assert result is not None
    assert result.type == ProviderMediaType.MOVIE


def test_naming_profile_namespaced_field_is_valid_only_when_registered():
    registry = MetadataRegistry()
    profile = NamingProfile(
        key="custom",
        content_profile="custom",
        fields=(NamingField(key="custom.content_id", label="内容编号"),),
    )
    register_naming_profile(profile, registry=registry, plugin_id="p1")

    assert "custom.content_id" in naming_field_keys(registry)
    assert naming_field_catalog(registry)[0]["label"] == "内容编号"

    assert validate("{custom.content_id}")["ok"] is False
    assert validate("{custom.content_id}", naming_field_keys(registry))["ok"] is True


def test_naming_profile_unregisters_by_plugin():
    registry = MetadataRegistry()
    profile = NamingProfile(
        key="custom",
        content_profile="custom",
        fields=(NamingField(key="custom.content_id", label="内容编号"),),
    )
    register_naming_profile(profile, registry=registry, plugin_id="p1")
    registry.unregister_plugin("p1")

    assert naming_field_keys(registry) == set()


def test_naming_profile_resolver_renders_field_value():
    from types import SimpleNamespace

    from app.media.metadata.naming import render_naming_fields

    registry = MetadataRegistry()
    profile = NamingProfile(
        key="custom-render",
        content_profile="default",
        fields=(
            NamingField(
                key="custom.content_id",
                label="编号",
                resolver=lambda media, snapshot: "ABC-123",
            ),
        ),
    )
    register_naming_profile(profile, registry=registry, plugin_id="p-render")

    values = render_naming_fields(
        SimpleNamespace(type=ProviderMediaType.MOVIE),
        None,
        registry=registry,
    )

    assert values == {"custom.content_id": "ABC-123"}


def test_parser_profile_short_circuits_unified_parser():
    from app.media.metadata.parsing import ParserChain
    from app.media.parser.base import ParserResult
    from app.media.parser.unified import UnifiedParser

    class _Profile:
        key = "custom-parser"
        content_profile = "custom"
        priority = 100

        def extract(self, title, subtitle=""):
            if "ABC-123" not in title:
                return None
            result = ParserResult(title_cn="自定义识别", type=ProviderMediaType.MOVIE, confidence=0.99)
            result.content_profile = "custom"
            result.anchor_provider = "content_id"
            result.anchor_external_id = "ABC-123"
            return result

    registry = MetadataRegistry()
    registry.register_profile("parser", "custom-parser", _Profile())
    parser = UnifiedParser(parser_chain=ParserChain(registry=registry))

    result = parser.parse("ABC-123.2024.1080p")

    assert result is not None
    assert result.title_cn == "自定义识别"
    assert result.content_profile == "custom"
    assert result.anchor_external_id == "ABC-123"

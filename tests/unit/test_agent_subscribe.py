"""Agent 订阅工具的类型/来源区分测试."""

from typing import cast

import pytest

from app.agent.tools.context import ToolContext
from app.agent.tools.handlers.subscribe import subscribe_add
from app.media.metadata import ProviderDescriptor
from app.media.metadata.registry import registry
from app.schemas.auth import UserContext


class _AdultProvider:
    descriptor = ProviderDescriptor(
        provider_key="javdb",
        display_name="JavDB",
        content_profiles=frozenset({"adult"}),
        search_mode="ADULT",
    )


@pytest.fixture(autouse=True)
def _register_adult_provider():
    registry.register_provider(_AdultProvider(), plugin_id="test")
    yield
    registry.unregister_provider("javdb", plugin_id="test")


class _AggregateProvider:
    descriptor = ProviderDescriptor(
        provider_key="aggregate",
        display_name="Aggregate",
        content_profiles=frozenset({"default"}),
        virtual=True,
    )


@pytest.fixture
def aggregate_provider():
    registry.register_provider(_AggregateProvider(), plugin_id="test-aggregate")
    yield
    registry.unregister_provider("aggregate", plugin_id="test-aggregate")


class _FakeSubscribeService:
    def __init__(self):
        self.kwargs: dict = {}

    def add_rss_subscribe(self, **kwargs):
        self.kwargs = kwargs
        return 0, "ok", None


class _FakeContext:
    def __init__(self, service, permissions=None, metadata_service=None):
        self.subscribe_service = service
        self.metadata_service = metadata_service
        self._user = UserContext(
            user_id=1,
            username="tester",
            level=0,
            permissions=permissions or [],
            role_codes=[],
        )

    def user_context(self, user_id):
        return self._user


def test_agent_subscribe_javdb_uses_adult_profile_and_provider_anchor():
    service = _FakeSubscribeService()
    ctx = _FakeContext(service, ["metadata:private:view"])

    result = subscribe_add(
        cast(ToolContext, ctx),
        "SSIS-001",
        provider="javdb",
        external_id="AbCdEf",
        content_id="SSIS-001",
    )

    assert result.success
    assert service.kwargs["content_profile"] == "adult"
    assert service.kwargs["metadata_ref"] == "javdb:AbCdEf"
    assert service.kwargs["mediaid"] == "javdb:AbCdEf"
    assert service.kwargs["keyword"] == "SSIS-001"
    assert service.kwargs["metadata_policy"] == "provider_only:adult"


def test_agent_subscribe_tmdb_uses_legacy_mediaid():
    service = _FakeSubscribeService()
    ctx = _FakeContext(service)

    result = subscribe_add(
        cast(ToolContext, ctx),
        "Dune: Part Two",
        provider="tmdb",
        external_id="693134",
        media_type="movie",
    )

    assert result.success
    assert service.kwargs["content_profile"] == "default"
    assert service.kwargs["mediaid"] == "693134"
    assert service.kwargs["metadata_ref"] is None


def test_agent_subscribe_adult_requires_private_permission():
    service = _FakeSubscribeService()
    ctx = _FakeContext(service)

    result = subscribe_add(cast(ToolContext, ctx), "SSIS-001", provider="javdb", external_id="AbCdEf")

    assert not result.success
    assert "metadata:private:view" in result.error
    assert service.kwargs == {}


def test_default_subscribe_setting_is_profile_aware():
    from app.domain.enums import SystemConfigKey
    from app.domain.mediatypes import MediaType
    from app.services.subscribe.management.add_service import SubscribeAddService

    keys = {
        SystemConfigKey.DefaultSubscribeSettingMovie: {"pix": "1080p"},
        f"{SystemConfigKey.DefaultSubscribeSettingMovie.value}::adult": {"pix": "4K"},
    }

    class _Config:
        def get(self, key):
            return keys.get(key) if not isinstance(key, str) else keys.get(key, {})

    service = SubscribeAddService.__new__(SubscribeAddService)
    service._system_config = _Config()

    assert service._default_setting_for(MediaType.MOVIE, "adult") == {"pix": "4K"}
    assert service._default_setting_for(MediaType.MOVIE, "default") == {"pix": "1080p"}


def test_agent_subscribe_resolves_provider_when_external_id_missing():
    service = _FakeSubscribeService()

    class _Metadata:
        def search(self, **kwargs):
            return [{"ref": {"provider": "javdb", "external_id": "AbCdEf"}}]

    ctx = _FakeContext(service, ["metadata:private:view"], _Metadata())

    result = subscribe_add(
        cast(ToolContext, ctx),
        "SSIS-001",
        provider="javdb",
        content_id="SSIS-001",
    )

    assert result.success
    assert service.kwargs["metadata_ref"] == "javdb:AbCdEf"
    assert service.kwargs["mediaid"] == "javdb:AbCdEf"


def test_web_search_uses_profile_default_sites():
    from app.domain.enums import SystemConfigKey
    from app.domain.mediatypes import MediaType
    from app.services.search_web_entry import _apply_default_sites

    keys = {
        f"{SystemConfigKey.DefaultSubscribeSettingMovie.value}::adult": {"search_sites": ["M-Team"]},
    }

    class _Config:
        def get(self, key):
            return keys.get(key, {})

    filter_args = {}
    _apply_default_sites(filter_args, MediaType.MOVIE, _Config(), "adult")

    assert filter_args["site"] == ["M-Team"]


def test_agent_subscribe_aggregate_resolves_real_provider_and_poster(aggregate_provider):
    service = _FakeSubscribeService()

    class _Metadata:
        def search(self, **kwargs):
            return [
                {
                    "provider": "javdb",
                    "title": "ABC-123 测试标题",
                    "poster": "https://img.example/abc123.jpg",
                    "ref": {"provider": "javdb", "external_id": "AbCdEf"},
                }
            ]

    ctx = _FakeContext(service, ["metadata:private:view"], _Metadata())

    result = subscribe_add(
        cast(ToolContext, ctx),
        "ABC-123",
        provider="aggregate",
        external_id="ABC-123",
        content_id="ABC-123",
    )

    assert result.success
    assert service.kwargs["metadata_ref"] == "javdb:AbCdEf"
    assert service.kwargs["image"] == "https://img.example/abc123.jpg"
    data = cast(dict, result.data)
    assert data["provider"] == "javdb"


def test_agent_subscribe_aggregate_without_exact_match_is_rejected(aggregate_provider):
    service = _FakeSubscribeService()

    class _Metadata:
        def search(self, **kwargs):
            return [
                {
                    "provider": "javdb",
                    "title": "ABC-124 其他内容",
                    "poster": "https://img.example/abc124.jpg",
                    "ref": {"provider": "javdb", "external_id": "XyZ789"},
                }
            ]

    ctx = _FakeContext(service, ["metadata:private:view"], _Metadata())

    result = subscribe_add(
        cast(ToolContext, ctx),
        "ABC-123",
        provider="aggregate",
        external_id="ABC-123",
        content_id="ABC-123",
    )

    assert not result.success
    assert "未找到 ABC-123" in result.error
    assert service.kwargs == {}

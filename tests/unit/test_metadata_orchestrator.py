"""MetadataOrchestrator 单元测试（fake provider，无网络）."""

from dataclasses import replace

from app.domain.media_types import MediaKind, ProviderMediaType
from app.domain.mediatypes import MediaType
from app.media.metadata import (
    EpisodeRecord,
    MetadataOrchestrator,
    ProviderCapability,
    ProviderDescriptor,
    ProviderRecord,
    ProviderRef,
    get_preset,
)
from app.media.metadata.errors import ProviderTimeout, ProviderUnavailable
from app.media.metadata.registry import MetadataRegistry


class _FakeProvider:
    def __init__(self, key, record=None, error=None, capabilities=None):
        self.descriptor = ProviderDescriptor(
            provider_key=key,
            display_name=key,
            capabilities=frozenset(capabilities or {ProviderCapability.DETAIL}),
            provider_media_types=frozenset({ProviderMediaType.SERIES}),
            media_kinds=frozenset({MediaKind.EPISODIC}),
        )
        self._record = record
        self._error = error

    def detail(self, ref, ctx):
        if self._error:
            raise self._error
        return self._record


def _record(provider: str, **kwargs) -> ProviderRecord:
    return ProviderRecord(
        provider=provider,
        external_id=f"{provider}-1",
        refs=[ProviderRef(provider=provider, external_id=f"{provider}-1")],
        media_type=MediaType.TV,
        **kwargs,
    )


def _tmdb_tv():
    return _record(
        "tmdb",
        title="TMDB 标题",
        episodes=[EpisodeRecord(season_number=1, episode_number=1)],
    )


def test_orchestrator_fetches_and_composes():
    reg = MetadataRegistry()
    reg.register_provider(
        _FakeProvider("tmdb", _tmdb_tv(), capabilities={ProviderCapability.DETAIL, ProviderCapability.EPISODES})
    )
    reg.register_provider(_FakeProvider("douban", _record("douban", title="豆瓣标题", overview="中文简介")))
    orchestrator = MetadataOrchestrator(reg)

    result = orchestrator.compose(
        "id-1",
        [ProviderRef(provider="tmdb", external_id="tmdb-1"), ProviderRef(provider="douban", external_id="douban-1")],
        get_preset("douban_primary"),
    )

    assert result.metadata is not None
    assert len(result.records) == 2
    assert result.errors == []
    assert result.metadata.fields["title"].value == "豆瓣标题"
    assert len(result.metadata.episodes) == 1


def test_orchestrator_degrades_on_provider_error():
    reg = MetadataRegistry()
    reg.register_provider(
        _FakeProvider("tmdb", _tmdb_tv(), capabilities={ProviderCapability.DETAIL, ProviderCapability.EPISODES})
    )
    reg.register_provider(_FakeProvider("douban", error=ProviderTimeout("douban", "timeout")))
    orchestrator = MetadataOrchestrator(reg)

    result = orchestrator.compose(
        "id-1",
        [ProviderRef(provider="tmdb", external_id="tmdb-1"), ProviderRef(provider="douban", external_id="douban-1")],
        get_preset("douban_primary"),
    )

    assert result.metadata is not None
    assert result.metadata.fields["title"].value == "TMDB 标题"
    assert result.degraded is True
    assert isinstance(result.errors[0], ProviderTimeout)


def test_orchestrator_records_unregistered_provider():
    reg = MetadataRegistry()
    reg.register_provider(_FakeProvider("tmdb", _record("tmdb", title="TMDB 标题")))
    orchestrator = MetadataOrchestrator(reg)

    result = orchestrator.compose(
        "id-1",
        [ProviderRef(provider="tmdb", external_id="tmdb-1"), ProviderRef(provider="missing", external_id="x")],
        get_preset("tmdb_primary"),
    )

    assert result.metadata is not None
    assert any(isinstance(error, ProviderUnavailable) for error in result.errors)


def test_orchestrator_requires_primary_when_partial_disallowed():
    reg = MetadataRegistry()
    reg.register_provider(_FakeProvider("tmdb", error=ProviderTimeout("tmdb", "timeout")))
    reg.register_provider(_FakeProvider("douban", _record("douban", title="豆瓣标题")))
    orchestrator = MetadataOrchestrator(reg)
    policy = get_preset("tmdb_primary")
    strict_policy = replace(policy, allow_partial=False)

    result = orchestrator.compose(
        "id-1",
        [ProviderRef(provider="tmdb", external_id="tmdb-1"), ProviderRef(provider="douban", external_id="douban-1")],
        strict_policy,
    )

    assert result.metadata is None
    assert result.records
    assert result.degraded is True


def test_orchestrator_deduplicates_refs():
    calls = []

    class _CountingProvider(_FakeProvider):
        def detail(self, ref, ctx):
            calls.append(ref)
            return super().detail(ref, ctx)

    reg = MetadataRegistry()
    reg.register_provider(_CountingProvider("tmdb", _record("tmdb", title="TMDB")))
    orchestrator = MetadataOrchestrator(reg)

    orchestrator.compose(
        "id-1",
        [
            ProviderRef(provider="tmdb", external_id="tmdb-1"),
            ProviderRef(provider="tmdb", external_id="tmdb-1"),
        ],
        get_preset("tmdb_primary"),
    )

    assert len(calls) == 1


def test_orchestrator_caches_provider_records():
    calls = []

    class _CountingProvider(_FakeProvider):
        def detail(self, ref, ctx):
            calls.append(ref)
            return super().detail(ref, ctx)

    reg = MetadataRegistry()
    reg.register_provider(_CountingProvider("tmdb", _record("tmdb", title="缓存")))
    orchestrator = MetadataOrchestrator(reg, cache_ttl_seconds=60)

    refs = [ProviderRef(provider="tmdb", external_id="tmdb-1")]
    first = orchestrator.compose("id", refs, get_preset("tmdb_primary"))
    second = orchestrator.compose("id", refs, get_preset("tmdb_primary"))

    assert first.metadata is not None and second.metadata is not None
    assert len(calls) == 1
    orchestrator.clear_cache()
    orchestrator.compose("id", refs, get_preset("tmdb_primary"))
    assert len(calls) == 2


def test_orchestrator_circuit_breaker_stops_calling_failing_provider():
    calls = []

    class _FailingProvider(_FakeProvider):
        descriptor = ProviderDescriptor(
            provider_key="tmdb",
            display_name="tmdb",
            capabilities=frozenset({ProviderCapability.DETAIL}),
            circuit_failures=2,
            circuit_cooldown_seconds=60,
        )

        def detail(self, ref, ctx):
            calls.append(ref)
            raise ProviderTimeout("tmdb", "timeout")

    reg = MetadataRegistry()
    reg.register_provider(_FailingProvider("tmdb"))
    orchestrator = MetadataOrchestrator(reg)
    refs = [ProviderRef(provider="tmdb", external_id="1")]

    for _ in range(4):
        orchestrator.compose("id", refs, get_preset("tmdb_primary"))

    assert len(calls) == 3

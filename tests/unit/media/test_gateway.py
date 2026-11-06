"""元数据网关缓存与请求合并测试."""

import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.domain.mediatypes import MediaType
from app.media.metadata.gateway import MetadataContext, MetadataGateway


def test_resolve_by_title_reuses_cache_for_same_context():
    service = MagicMock()
    media_service = MagicMock()
    media_service.get_media_info.return_value = SimpleNamespace(title="Demo")
    gateway = MetadataGateway(service, media_service=media_service, default_ttl=60)
    ctx = MetadataContext(
        user_id=1,
        permissions=frozenset({"metadata:private:view"}),
        content_profile="anime",
        allow_private=True,
    )

    first = gateway.resolve_by_title("Demo", media_type=MediaType.TV, year="2024", context=ctx)
    second = gateway.resolve_by_title("Demo", media_type=MediaType.TV, year="2024", context=ctx)

    assert first is not None and second is not None
    assert first.title == second.title
    assert media_service.get_media_info.call_count == 1


def test_resolve_by_title_cache_isolated_by_year_and_permissions():
    service = MagicMock()
    media_service = MagicMock()
    media_service.get_media_info.return_value = SimpleNamespace(title="Demo")
    gateway = MetadataGateway(service, media_service=media_service, default_ttl=60)

    gateway.resolve_by_title(
        "Demo",
        media_type=MediaType.TV,
        year="2024",
        context=MetadataContext(content_profile="default", permissions=frozenset({"a"})),
    )
    gateway.resolve_by_title(
        "Demo",
        media_type=MediaType.TV,
        year="2025",
        context=MetadataContext(content_profile="default", permissions=frozenset({"a"})),
    )
    gateway.resolve_by_title(
        "Demo",
        media_type=MediaType.TV,
        year="2024",
        context=MetadataContext(content_profile="anime", permissions=frozenset({"b"})),
    )

    assert media_service.get_media_info.call_count == 3


def test_resolve_reuses_cached_envelope():
    service = MagicMock()
    service.compose_for_ref.return_value = {"title": "Demo"}
    gateway = MetadataGateway(service, default_ttl=60)
    ctx = MetadataContext()

    first = gateway.resolve("tmdb", "1", context=ctx, media_type=MediaType.MOVIE)
    second = gateway.resolve("tmdb", "1", context=ctx, media_type=MediaType.MOVIE)

    assert first is not None and second is not None
    assert second.cache_hit is True
    assert service.compose_for_ref.call_count == 1


def test_resolve_singleflight_for_same_ref():
    service = MagicMock()

    def slow(*_args, **_kwargs):
        time.sleep(0.2)
        return {"title": "Demo"}

    service.compose_for_ref.side_effect = slow
    gateway = MetadataGateway(service)
    ctx = MetadataContext()
    results = []

    def worker():
        results.append(gateway.resolve("tmdb", "singleflight", context=ctx, media_type=MediaType.MOVIE))

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert all(item is not None for item in results)
    assert service.compose_for_ref.call_count == 1


def test_lookup_reuses_cached_detail_and_passes_context():
    service = MagicMock()
    service.lookup.return_value = {"title": "Demo"}
    service.find_identity_id.return_value = "identity-demo"
    service.latest_snapshot_record.return_value = SimpleNamespace(ID=9)
    gateway = MetadataGateway(service, default_ttl=60)
    ctx = MetadataContext(
        user_id=7,
        permissions=frozenset({"metadata:private:view"}),
        purpose="test",
        allow_private=True,
    )

    first = gateway.lookup("demo", "DEMO-1", context=ctx, media_type=MediaType.MOVIE)
    second = gateway.lookup("demo", "DEMO-1", context=ctx, media_type=MediaType.MOVIE)

    assert first == {"title": "Demo"} and second == first
    service.lookup.assert_called_once_with(
        "demo",
        "DEMO-1",
        media_type=MediaType.MOVIE,
        scope="default",
        allow_private=True,
        content_profile="default",
        permissions={"metadata:private:view"},
    )


def test_lookup_singleflight_for_same_ref():
    service = MagicMock()

    def slow(*_args, **_kwargs):
        time.sleep(0.2)
        return {"title": "Demo"}

    service.lookup.side_effect = slow
    gateway = MetadataGateway(service)
    ctx = MetadataContext()
    results = []

    def worker():
        results.append(gateway.lookup("demo", "DEMO-1", context=ctx, media_type=MediaType.MOVIE))

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert all(item is not None for item in results)
    assert service.lookup.call_count == 1


def test_lookup_returns_stale_when_provider_fails():
    service = MagicMock()
    service.lookup.side_effect = [{"title": "Demo"}, RuntimeError("rate limited")]
    gateway = MetadataGateway(service)
    ctx = MetadataContext()

    first = gateway.lookup("demo", "DEMO-1", context=ctx, media_type=MediaType.MOVIE)
    second = gateway.lookup("demo", "DEMO-1", context=ctx, media_type=MediaType.MOVIE, freshness="force")

    assert first == {"title": "Demo"}
    assert second == first


def test_resolve_many_deduplicates_same_ref():
    service = MagicMock()
    service.compose_for_ref.return_value = {"title": "Demo"}
    gateway = MetadataGateway(service)

    result = gateway.resolve_many(
        [("demo", "DEMO-1"), ("demo", "DEMO-1")],
        context=MetadataContext(),
        media_type=MediaType.MOVIE,
    )

    assert list(result) == [("demo", "DEMO-1")]
    assert service.compose_for_ref.call_count == 1


def test_private_metadata_requires_permission():
    service = MagicMock()
    service.provider_descriptor.return_value = SimpleNamespace(
        visibility="private",
        required_permission="metadata:private:view",
    )
    gateway = MetadataGateway(service)
    media = SimpleNamespace(anchor_provider="private_provider")

    with pytest.raises(PermissionError):
        gateway.hydrate_media(media, context=MetadataContext())

    gateway.hydrate_media(
        media,
        context=MetadataContext(
            allow_private=True,
            permissions=frozenset({"metadata:private:view"}),
        ),
    )


def test_l2_cache_is_shared_between_gateway_instances():
    service = MagicMock()
    service.compose_for_ref.return_value = {"title": "L2 Demo"}
    first = MetadataGateway(service)
    second = MetadataGateway(service)
    first.clear()
    ctx = MetadataContext()

    first.resolve("tmdb", "l2-demo", context=ctx, media_type=MediaType.MOVIE)
    second.resolve("tmdb", "l2-demo", context=ctx, media_type=MediaType.MOVIE)

    assert service.compose_for_ref.call_count == 1
    assert second.metrics()["l2_hit"] >= 1

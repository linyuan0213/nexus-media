"""元数据网关缓存与请求合并测试."""

import threading
import time
from unittest.mock import MagicMock

from app.domain.mediatypes import MediaType
from app.media.metadata.gateway import MetadataContext, MetadataGateway


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
        results.append(gateway.resolve("tmdb", "1", context=ctx, media_type=MediaType.MOVIE))

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert all(item is not None for item in results)
    assert service.compose_for_ref.call_count == 1

"""RedisStore 可用性缓存测试：避免每次操作都 PING Redis，防止阻塞调用方/事件循环."""

import time
from unittest.mock import MagicMock

import pytest

from app.infrastructure.redis import store as store_module
from app.infrastructure.redis.store import RedisStore


@pytest.fixture(autouse=True)
def _enable_redis(monkeypatch):
    monkeypatch.setattr(store_module.redis_cfg, "enabled", True)


def _store_with_client() -> tuple[RedisStore, MagicMock]:
    store = RedisStore()
    client = MagicMock()
    store._client = client
    store._available = True
    return store, client


def test_is_available_uses_cache_without_ping():
    store, client = _store_with_client()
    store._last_ok = time.time()

    assert store.is_available() is True
    client.ping.assert_not_called()


def test_is_available_rechecks_after_interval():
    store, client = _store_with_client()
    store._last_ok = time.time() - (RedisStore._RECHECK_INTERVAL + 1)

    assert store.is_available() is True
    client.ping.assert_called_once()

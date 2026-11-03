"""全局索引器 provider 注册表，供插件启用/禁用时自动注册和注销。"""

from __future__ import annotations

import threading

from .provider import IndexerProvider
from .registry import IndexerProviderRegistry

_registry = IndexerProviderRegistry()
_owners: dict[str, set[str]] = {}
_lock = threading.RLock()


def get_global_registry() -> IndexerProviderRegistry:
    return _registry


def register_indexer_provider(provider: IndexerProvider, plugin_id: str) -> None:
    provider_id = provider.provider_id
    with _lock:
        _registry.register(provider, replace=True)
        _owners.setdefault(plugin_id, set()).add(provider_id)


def unregister_plugin_indexers(plugin_id: str) -> None:
    with _lock:
        for provider_id in _owners.pop(plugin_id, set()):
            _registry.unregister(provider_id, close=True)

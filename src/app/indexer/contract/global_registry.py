"""全局索引器 provider 注册表，供插件启用/禁用时自动注册和注销。"""

from __future__ import annotations

import threading

from .provider import IndexerProvider
from .registry import IndexerProviderRegistry

_registry = IndexerProviderRegistry()
_owners: dict[str, str] = {}
_lock = threading.RLock()


def get_global_registry() -> IndexerProviderRegistry:
    return _registry


def register_indexer_provider(provider: IndexerProvider, plugin_id: str) -> None:
    provider_id = provider.provider_id
    with _lock:
        owner = _owners.get(provider_id)
        if owner is not None and owner != plugin_id:
            raise ValueError(f"索引器 provider {provider_id} 已属于插件 {owner}")
        _registry.register(provider, replace=True)
        _owners[provider_id] = plugin_id


def unregister_plugin_indexers(plugin_id: str) -> None:
    with _lock:
        owned = [provider_id for provider_id, owner in _owners.items() if owner == plugin_id]
        for provider_id in owned:
            _owners.pop(provider_id, None)
            _registry.unregister(provider_id, close=True)

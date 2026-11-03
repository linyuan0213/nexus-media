"""索引器 provider 注册表。"""

from __future__ import annotations

import threading

from .provider import IndexerProvider


class IndexerProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, IndexerProvider] = {}
        self._lock = threading.RLock()

    def register(self, provider: IndexerProvider, *, replace: bool = False) -> None:
        provider_id = provider.provider_id.strip()
        if not provider_id:
            raise ValueError("索引器 provider_id 不能为空")
        with self._lock:
            if provider_id in self._providers and not replace:
                raise ValueError(f"索引器 provider 已存在: {provider_id}")
            self._providers[provider_id] = provider

    def unregister(self, provider_id: str, *, close: bool = True) -> None:
        with self._lock:
            provider = self._providers.pop(provider_id, None)
        if provider is not None and close:
            provider.close()

    def get(self, provider_id: str) -> IndexerProvider | None:
        with self._lock:
            return self._providers.get(provider_id)

    def list(self) -> list[IndexerProvider]:
        with self._lock:
            return list(self._providers.values())

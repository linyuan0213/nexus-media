"""索引器 provider 工厂：从配置创建并注册多个索引器实例。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .http import HttpIndexerProvider
from .provider import IndexerProvider
from .registry import IndexerProviderRegistry

ProviderFactory = Callable[[dict[str, Any]], IndexerProvider]


def _build_http(spec: dict[str, Any]) -> IndexerProvider:
    return HttpIndexerProvider(
        str(spec.get("base_url") or ""),
        token=spec.get("token"),
        timeout=float(spec.get("timeout") or 30),
        provider_id=str(spec.get("id") or "remote-indexer"),
        info_path=str(spec.get("info_path") or "/api/indexer/info"),
        search_path=str(spec.get("search_path") or "/api/indexer/search"),
        list_path=str(spec.get("list_path") or "/api/indexer/list"),
    )


_FACTORIES: dict[str, ProviderFactory] = {"http": _build_http}


def register_provider_factory(kind: str, factory: ProviderFactory) -> None:
    key = kind.strip().lower()
    if not key:
        raise ValueError("索引器 provider 类型不能为空")
    _FACTORIES[key] = factory


def build_provider(spec: dict[str, Any]) -> IndexerProvider:
    kind = str(spec.get("type") or "").strip().lower()
    factory = _FACTORIES.get(kind)
    if factory is None:
        raise ValueError(f"未知索引器 provider 类型: {kind}")
    return factory(spec)


def load_providers(registry: IndexerProviderRegistry, specs: list[dict[str, Any]]) -> None:
    for spec in specs:
        if spec.get("enabled", True):
            registry.register(build_provider(spec))

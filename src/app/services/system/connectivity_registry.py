"""动态外部依赖连通性目标注册表."""

from __future__ import annotations

from typing import Any

from app.core.settings import settings
from app.domain.connectivity import ConnectivityTarget
from app.media.metadata.providers.builtin import register_builtin_providers
from app.media.metadata.registry import registry as metadata_registry

_INFRA_TARGETS: tuple[ConnectivityTarget, ...] = (
    ConnectivityTarget(
        "webservice.fanart.tv",
        "webservice.fanart.tv",
        "https://webservice.fanart.tv/",
        "metadata",
        use_proxy=True,
        order=30,
    ),
    ConnectivityTarget("api.github.com", "api.github.com", "https://api.github.com/", "external", order=40),
)
_plugin_targets: dict[str, list[ConnectivityTarget]] = {}


def _normalize(plugin_id: str, item: Any) -> ConnectivityTarget | None:
    if isinstance(item, ConnectivityTarget):
        return item
    if not isinstance(item, dict):
        return None
    key = str(item.get("key") or item.get("target") or "").strip()
    url = str(item.get("url") or "").strip()
    if not key or not url:
        return None
    return ConnectivityTarget(
        key=key,
        label=str(item.get("label") or key),
        url=url,
        category=str(item.get("category") or plugin_id),
        requires_auth=bool(item.get("requires_auth")),
        probe=str(item.get("probe") or "http"),
        use_proxy=bool(item.get("use_proxy") if "use_proxy" in item else item.get("proxy", False)),
        probe_fn=item.get("probe_fn") if callable(item.get("probe_fn")) else None,
        order=int(item.get("order") or 100),
    )


def register_plugin_targets(plugin_id: str, items: list[Any]) -> None:
    normalized = [target for item in items if (target := _normalize(plugin_id, item)) is not None]
    if normalized:
        _plugin_targets[str(plugin_id)] = normalized


def unregister_plugin_targets(plugin_id: str) -> None:
    _plugin_targets.pop(str(plugin_id), None)


def _extra_targets() -> list[ConnectivityTarget]:
    config = settings.get("nettest") or {}
    result = []
    for item in config.get("extra_targets") or []:
        target = _normalize("config", item)
        if target:
            result.append(target)
    return result


def _provider_targets() -> list[ConnectivityTarget]:
    """从已注册的元数据 provider descriptor 自动收集目标."""
    if any(metadata_registry.get_provider(key) is None for key in ("tmdb", "douban", "bangumi")):
        register_builtin_providers(metadata_registry)
    result: list[ConnectivityTarget] = []
    for provider in metadata_registry.list_providers():
        descriptor = getattr(provider, "descriptor", None)
        for item in getattr(descriptor, "connectivity_targets", ()) or ():
            target = _normalize(getattr(descriptor, "provider_key", "provider"), item)
            if target:
                result.append(target)
    return result


def list_targets() -> list[ConnectivityTarget]:
    merged: dict[str, ConnectivityTarget] = {}
    for target in (*_INFRA_TARGETS, *_provider_targets(), *_extra_targets()):
        merged[target.key] = target
    for items in _plugin_targets.values():
        for target in items:
            merged.setdefault(target.key, target)
    return sorted(merged.values(), key=lambda item: (item.order, item.label, item.key))


def resolve_target(key: str) -> ConnectivityTarget | None:
    key = str(key or "").strip()
    if not key:
        return None
    for target in list_targets():
        if target.key == key or target.url.rstrip("/") == key.rstrip("/"):
            return target
    return None

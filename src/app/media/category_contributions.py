"""插件分类贡献注册表."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from app.plugin_sdk.category import CategoryContribution

_LOCK = threading.RLock()
_CONTRIBUTIONS: dict[str, CategoryContribution] = {}
_OWNERS: dict[str, str] = {}
_PERSISTERS: dict[str, Callable[[list[dict[str, Any]]], None]] = {}


def register_category_contribution(
    contribution: CategoryContribution,
    plugin_id: str,
    persist: Callable[[list[dict[str, Any]]], None] | None = None,
) -> None:
    if not isinstance(contribution, CategoryContribution):
        raise TypeError("contribution 必须是 CategoryContribution")
    namespace = contribution.namespace.strip()
    if namespace != namespace.lower() or not namespace.replace("_", "").replace("-", "").isalnum():
        raise ValueError("分类贡献 namespace 只能包含小写字母、数字、_ 和 -")
    with _LOCK:
        existing = _CONTRIBUTIONS.get(namespace)
        if existing is not None and _OWNERS.get(namespace) != plugin_id:
            raise ValueError(f"分类贡献 namespace 已被注册: {namespace} (plugin={plugin_id})")
        _CONTRIBUTIONS[namespace] = contribution
        _OWNERS[namespace] = plugin_id
        if persist is not None:
            _PERSISTERS[namespace] = persist


def unregister_category_contribution(namespace: str, plugin_id: str | None = None) -> None:
    with _LOCK:
        _CONTRIBUTIONS.pop(namespace, None)
        _OWNERS.pop(namespace, None)
        _PERSISTERS.pop(namespace, None)


def unregister_plugin_contributions(plugin_id: str) -> None:
    with _LOCK:
        namespaces = [namespace for namespace, owner in _OWNERS.items() if owner == plugin_id]
        for namespace in namespaces:
            _CONTRIBUTIONS.pop(namespace, None)
            _OWNERS.pop(namespace, None)
            _PERSISTERS.pop(namespace, None)


def get_category_contributions(media_type: str | None = None, scope: str | None = None) -> list[CategoryContribution]:
    with _LOCK:
        values = list(_CONTRIBUTIONS.values())
    if media_type is not None:
        values = [item for item in values if media_type in item.media_types]
    if scope is not None:
        values = [item for item in values if item.scope == scope]
    return sorted(values, key=lambda item: item.priority, reverse=True)


def clear_category_contributions() -> None:
    with _LOCK:
        _CONTRIBUTIONS.clear()
        _OWNERS.clear()
        _PERSISTERS.clear()


def core_category_rules(media_type: str) -> dict[str, Any]:
    """合并 scope=core 的插件分类；插件分类优先于内置同名分类."""
    result: dict[str, Any] = {}
    for contribution in get_category_contributions(media_type, scope="core"):
        result.update(contribution.categories)
    return result


def get_category_tabs() -> list[dict[str, Any]]:
    """分类页标签：核心三项 + 插件贡献标签."""
    tabs: list[dict[str, Any]] = [
        {"key": "movie", "label": "电影"},
        {"key": "tv", "label": "电视剧"},
        {"key": "anime", "label": "动漫"},
    ]
    for contribution in get_category_contributions():
        if not contribution.tab_key or not contribution.tab_label:
            continue
        tabs.append(
            {
                "key": contribution.tab_key,
                "label": contribution.tab_label,
                "namespace": contribution.namespace,
                "order": contribution.tab_order,
                "fields": list(contribution.fields),
                "field_labels": dict(contribution.field_labels),
                "categories": [
                    {
                        "name": key,
                        "label": contribution.category_labels.get(key, key),
                        "enabled": contribution.category_enabled.get(key, True),
                        "rules": rules,
                    }
                    for key, rules in contribution.categories.items()
                ],
            }
        )
    return tabs


def update_category_contribution(namespace: str, categories: list[dict[str, Any]]) -> None:
    persist = _PERSISTERS.get(namespace)
    if persist is None:
        raise ValueError(f"分类贡献不支持编辑: {namespace}")
    persist(categories)


def get_category_contribution_for_tab(tab_key: str) -> CategoryContribution | None:
    for contribution in get_category_contributions():
        if contribution.tab_key == tab_key:
            return contribution
    return None


def update_category_contribution_by_tab(tab_key: str, categories: list[dict[str, Any]]) -> None:
    contribution = get_category_contribution_for_tab(tab_key)
    if contribution is None:
        return
    update_category_contribution(contribution.namespace, categories)

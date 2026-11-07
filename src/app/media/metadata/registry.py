"""Provider 与 Profile 注册表.

约束：
- key 全局唯一，核心内置 key 不可被插件覆盖；
- 注册幂等，同 key 重复注册视为替换；
- 插件禁用/卸载时按 plugin_id 批量注销。
"""

from __future__ import annotations

import contextlib
import threading
from dataclasses import dataclass
from typing import Any

from app.domain.media_types import ProviderMediaType, media_type_registry

from .models import ProviderCapability, ProviderDescriptor

PROFILE_KINDS = frozenset({"content", "match", "parser", "naming", "nfo"})
BUILTIN_PLUGIN_ID = "builtin"


@dataclass(frozen=True)
class _Entry:
    plugin_id: str
    obj: Any


class MetadataRegistry:
    """线程安全的元数据扩展注册表."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._providers: dict[str, _Entry] = {}
        self._discoveries: dict[str, _Entry] = {}
        self._profiles: dict[str, dict[str, _Entry]] = {kind: {} for kind in PROFILE_KINDS}
        self._revision = 0

    @property
    def revision(self) -> int:
        """注册表版本；provider/profile 变化后递增，供缓存命名空间失效."""
        with self._lock:
            return self._revision

    # ---------- provider ----------

    def register_provider(
        self,
        provider: Any,
        *,
        plugin_id: str = BUILTIN_PLUGIN_ID,
        declared_key: str | None = None,
    ) -> None:
        descriptor = _descriptor_of(provider)
        self._register_entry(
            self._providers,
            descriptor.provider_key,
            provider,
            plugin_id=plugin_id,
            declared_key=declared_key,
        )

    def unregister_provider(self, provider_key: str, *, plugin_id: str | None = None) -> None:
        self._unregister_entry(self._providers, provider_key, plugin_id=plugin_id)

    def get_provider(self, provider_key: str) -> Any | None:
        with self._lock:
            entry = self._providers.get(provider_key)
            return entry.obj if entry else None

    def is_builtin_provider(self, provider_key: str) -> bool:
        """provider 是否由核心内置注册（非插件）。"""
        with self._lock:
            entry = self._providers.get(provider_key)
            return bool(entry and entry.plugin_id == BUILTIN_PLUGIN_ID)

    def list_providers(
        self,
        *,
        capability: ProviderCapability | str | None = None,
        content_profile: str | None = None,
        media_type: ProviderMediaType | None = None,
        visibility: str | None = None,
    ) -> list[Any]:
        with self._lock:
            providers = [entry.obj for entry in self._providers.values()]
        return [
            provider
            for provider in providers
            if _provider_matches(provider, capability, content_profile, media_type, visibility)
        ]

    def resolve_ref_prefix(self, prefix: str) -> str:
        """按 provider descriptor 声明的 ref_prefixes 解析 provider key."""
        normalized = str(prefix or "").strip().upper()
        if not normalized:
            return ""
        with self._lock:
            providers = [entry.obj for entry in self._providers.values()]
        for provider in providers:
            descriptor = _descriptor_of(provider)
            prefixes = {str(item).upper() for item in descriptor.ref_prefixes}
            if normalized in prefixes:
                return descriptor.provider_key
        return ""

    def search_mode_for_profile(self, content_profile: str | None) -> str:
        """由 provider descriptor 声明内容画像对应的站点搜索模式."""
        profile = str(content_profile or "").strip()
        if not profile:
            return ""
        with self._lock:
            providers = [entry.obj for entry in self._providers.values()]
        for provider in providers:
            descriptor = _descriptor_of(provider)
            if profile in descriptor.content_profiles and descriptor.search_mode:
                return descriptor.search_mode
        return ""

    def provider_detail_url(
        self,
        provider_key: str,
        external_id: str,
        media_type: ProviderMediaType | None = None,
    ) -> str:
        provider = self.get_provider(provider_key)
        if provider is None:
            return ""
        template = provider.descriptor.detail_url_template
        if not template:
            return ""
        type_value = "movie" if media_type == ProviderMediaType.MOVIE else "tv"
        return template.format(external_id=external_id, media_type=type_value)

    # ---------- discovery ----------

    def register_discovery_provider(
        self,
        provider: Any,
        *,
        plugin_id: str = BUILTIN_PLUGIN_ID,
        declared_key: str | None = None,
    ) -> None:
        descriptor = _descriptor_of(provider)
        self._register_entry(
            self._discoveries,
            descriptor.provider_key,
            provider,
            plugin_id=plugin_id,
            declared_key=declared_key,
        )

    def unregister_discovery_provider(self, provider_key: str, *, plugin_id: str | None = None) -> None:
        self._unregister_entry(self._discoveries, provider_key, plugin_id=plugin_id)

    def get_discovery_provider(self, provider_key: str) -> Any | None:
        with self._lock:
            entry = self._discoveries.get(provider_key)
            return entry.obj if entry else None

    def list_discovery_providers(
        self,
        *,
        content_profile: str | None = None,
        visibility: str | None = None,
    ) -> list[Any]:
        with self._lock:
            providers = [entry.obj for entry in self._discoveries.values()]
        result = []
        for provider in providers:
            descriptor = _descriptor_of(provider)
            if content_profile and descriptor.content_profiles and content_profile not in descriptor.content_profiles:
                continue
            if visibility and descriptor.visibility != visibility:
                continue
            result.append(provider)
        return result

    # ---------- profiles ----------

    def register_profile(
        self,
        kind: str,
        key: str,
        profile: Any,
        *,
        plugin_id: str = BUILTIN_PLUGIN_ID,
        declared_key: str | None = None,
    ) -> None:
        if kind not in PROFILE_KINDS:
            raise ValueError(f"未知 profile 类型: {kind}")
        self._register_entry(
            self._profiles[kind],
            key,
            profile,
            plugin_id=plugin_id,
            declared_key=declared_key,
        )

    def unregister_profile(self, kind: str, key: str, *, plugin_id: str | None = None) -> None:
        if kind not in PROFILE_KINDS:
            raise ValueError(f"未知 profile 类型: {kind}")
        self._unregister_entry(self._profiles[kind], key, plugin_id=plugin_id)

    def get_profile(self, kind: str, key: str) -> Any | None:
        if kind not in PROFILE_KINDS:
            return None
        with self._lock:
            entry = self._profiles[kind].get(key)
            return entry.obj if entry else None

    def list_profiles(self, kind: str) -> list[Any]:
        if kind not in PROFILE_KINDS:
            return []
        with self._lock:
            return [entry.obj for entry in self._profiles[kind].values()]

    # ---------- lifecycle ----------

    def unregister_plugin(self, plugin_id: str) -> None:
        removed: list[Any] = []
        with self._lock:
            for store in (self._providers, self._discoveries, *self._profiles.values()):
                for key in [k for k, entry in store.items() if entry.plugin_id == plugin_id]:
                    removed.append(store.pop(key).obj)
        if removed:
            with self._lock:
                self._revision += 1
        for obj in removed:
            hook = getattr(obj, "on_unregister", None)
            if callable(hook):
                with contextlib.suppress(Exception):
                    hook(plugin_id)

    def clear(self) -> None:
        with self._lock:
            self._providers.clear()
            self._discoveries.clear()
            for store in self._profiles.values():
                store.clear()
            self._revision += 1

    # ---------- internals ----------

    def _register_entry(
        self,
        store: dict[str, _Entry],
        key: str,
        obj: Any,
        *,
        plugin_id: str,
        declared_key: str | None,
    ) -> None:
        if not key:
            raise ValueError("注册 key 不能为空")
        if declared_key is not None and declared_key != key:
            raise ValueError(f"注册 key 与 manifest 声明不一致: {declared_key} != {key}")
        with self._lock:
            existing = store.get(key)
            if existing and existing.plugin_id != plugin_id:
                if existing.plugin_id == BUILTIN_PLUGIN_ID:
                    raise ValueError(f"内置 key 不可被插件覆盖: {key}")
                raise ValueError(f"key 已由插件 {existing.plugin_id} 注册，不能覆盖: {key}")
            store[key] = _Entry(plugin_id=plugin_id, obj=obj)
            self._revision += 1

    def _unregister_entry(self, store: dict[str, _Entry], key: str, *, plugin_id: str | None) -> None:
        with self._lock:
            entry = store.get(key)
            if not entry:
                return
            if plugin_id is not None and entry.plugin_id != plugin_id:
                raise ValueError(f"无权注销 key: {key}")
            store.pop(key, None)
            self._revision += 1


def _descriptor_of(provider: Any) -> ProviderDescriptor:
    descriptor = getattr(provider, "descriptor", None)
    if not isinstance(descriptor, ProviderDescriptor):
        raise ValueError("provider 必须暴露 ProviderDescriptor")
    return descriptor


def _provider_matches(
    provider: Any,
    capability: ProviderCapability | str | None,
    content_profile: str | None,
    media_type: ProviderMediaType | None,
    visibility: str | None,
) -> bool:
    descriptor = _descriptor_of(provider)
    if capability is not None:
        cap = ProviderCapability(capability) if isinstance(capability, str) else capability
        if cap not in descriptor.capabilities:
            return False
    if content_profile and descriptor.content_profiles and content_profile not in descriptor.content_profiles:
        return False
    if (
        media_type
        and descriptor.media_kinds
        and media_type_registry.resolve(media_type).kind not in descriptor.media_kinds
    ):
        return False
    return not (visibility and descriptor.visibility != visibility)


registry = MetadataRegistry()

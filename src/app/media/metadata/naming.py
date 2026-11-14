"""命名 Profile 扩展点.

插件字段使用命名空间 key（如 ``<profile>.content_id``），
核心字段目录保持原样，旧模板不受影响。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.domain.media_types import ProviderMediaType

from .registry import MetadataRegistry
from .registry import registry as global_registry


@dataclass(frozen=True)
class NamingField:
    key: str
    label: str
    desc: str = ""
    applies: str = "both"
    requires_media_service: bool = False
    resolver: Callable[[Any, Any], Any] | None = None


@dataclass(frozen=True)
class NamingProfile:
    key: str
    content_profile: str
    fields: tuple[NamingField, ...] = ()
    default_movie: str = ""
    default_tv: str = ""
    default_tv_season: str = ""
    templates: dict[str, str] = field(default_factory=dict)
    # 该 profile 的模板已经包含分类目录，核心转移不再额外拼接通用分类目录。
    provides_category: bool = False

    def field_keys(self) -> set[str]:
        return {item.key for item in self.fields}


def register_naming_profile(
    profile: NamingProfile,
    *,
    registry: MetadataRegistry | None = None,
    plugin_id: str = "builtin",
) -> None:
    target = registry or global_registry
    target.register_profile("naming", profile.key, profile, plugin_id=plugin_id)


def list_naming_profiles(registry: MetadataRegistry | None = None) -> list[NamingProfile]:
    target = registry or global_registry
    return [item for item in target.list_profiles("naming") if isinstance(item, NamingProfile)]


def naming_field_catalog(registry: MetadataRegistry | None = None) -> list[dict]:
    """返回所有命名 profile 注册的字段，供前端字段目录合并."""
    fields: dict[str, dict] = {}
    for profile in list_naming_profiles(registry):
        for item in profile.fields:
            fields.setdefault(
                item.key,
                {
                    "key": item.key,
                    "label": item.label,
                    "desc": item.desc,
                    "applies": item.applies,
                    "requires_ms": item.requires_media_service,
                    "profile": profile.key,
                },
            )
    return list(fields.values())


def naming_field_keys(registry: MetadataRegistry | None = None) -> set[str]:
    return {item["key"] for item in naming_field_catalog(registry)}


def render_naming_fields(
    media: Any,
    snapshot: Any = None,
    *,
    registry: MetadataRegistry | None = None,
) -> dict[str, Any]:
    """执行已注册 profile 的字段 resolver，供 get_format_dict 合并."""
    content_profile = getattr(media, "content_profile", None) or (
        "anime" if getattr(media, "type", None) == ProviderMediaType.ANIME else "default"
    )
    media_kind = (
        "tv" if getattr(media, "type", None) in {ProviderMediaType.SERIES, ProviderMediaType.ANIME} else "movie"
    )
    values: dict[str, Any] = {}
    for profile in list_naming_profiles(registry):
        if profile.content_profile not in {content_profile, "default"}:
            continue
        for item in profile.fields:
            if not item.resolver:
                continue
            if item.applies not in {"both", media_kind, content_profile}:
                continue
            try:
                value = item.resolver(media, snapshot)
            except Exception:
                continue
            if value not in (None, "", []):
                values[item.key] = value
    return values

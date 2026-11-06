"""合成策略与预设.

策略只描述字段优先级，不包含任何 provider 的具体实现。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

MergeMode = Literal["first", "union", "union_by_name", "primary_only", "namespaced"]


@dataclass(frozen=True)
class FieldRule:
    """单字段合成规则."""

    order: tuple[str, ...] = ()
    locale: str | None = None
    merge: MergeMode = "first"


@dataclass(frozen=True)
class MetadataPolicy:
    """一份可复用的合成策略."""

    key: str
    primary: str
    fallbacks: tuple[str, ...] = ()
    conflict: Literal["primary_wins", "first_non_empty", "manual"] = "primary_wins"
    field_rules: dict[str, FieldRule] = field(default_factory=dict)
    allow_partial: bool = True

    def order_for(self, field_name: str) -> tuple[str, ...]:
        rule = self.field_rules.get(field_name)
        if rule and rule.order:
            return rule.order
        return (self.primary, *self.fallbacks)

    def merge_for(self, field_name: str) -> MergeMode:
        rule = self.field_rules.get(field_name)
        return rule.merge if rule else "first"

    def locale_for(self, field_name: str) -> str | None:
        rule = self.field_rules.get(field_name)
        return rule.locale if rule else None

    @property
    def provider_order(self) -> tuple[str, ...]:
        return (self.primary, *self.fallbacks)


def _base_rules(primary: str, secondary: str) -> dict[str, FieldRule]:
    return {
        "title": FieldRule(order=(primary, secondary), locale="zh-Hans"),
        "original_title": FieldRule(order=(primary, secondary)),
        "overview": FieldRule(order=(primary, secondary), locale="zh-Hans"),
        # 图片/日期/时长始终优先 TMDB：豆瓣无 backdrop/logo，日期可能是重映日
        "poster": FieldRule(order=("tmdb", "douban")),
        "backdrop": FieldRule(order=("tmdb", "douban")),
        "release_date": FieldRule(order=("tmdb", "douban")),
        "runtime": FieldRule(order=("tmdb", "douban")),
        "genres": FieldRule(order=(primary, secondary), merge="union"),
        "tags": FieldRule(order=(primary, secondary), merge="union"),
        "credits": FieldRule(order=(primary, secondary), merge="union_by_name"),
        "ratings": FieldRule(order=(primary, secondary), merge="namespaced"),
    }


_PRESETS: dict[str, MetadataPolicy] = {
    "tmdb_primary": MetadataPolicy(
        key="tmdb_primary",
        primary="tmdb",
        fallbacks=("douban",),
        field_rules=_base_rules("tmdb", "douban"),
    ),
    "douban_primary": MetadataPolicy(
        key="douban_primary",
        primary="douban",
        fallbacks=("tmdb",),
        field_rules={
            **_base_rules("douban", "tmdb"),
            # 豆瓣锚点：所有可提供字段优先豆瓣，仅豆瓣缺失时回退 TMDB
            "poster": FieldRule(order=("douban", "tmdb")),
            "backdrop": FieldRule(order=("douban", "tmdb")),
            "release_date": FieldRule(order=("douban", "tmdb")),
            "runtime": FieldRule(order=("douban", "tmdb")),
        },
    ),
    "bangumi_primary": MetadataPolicy(
        key="bangumi_primary",
        primary="bangumi",
        fallbacks=("tmdb", "douban"),
        field_rules={
            "title": FieldRule(order=("bangumi", "douban", "tmdb"), locale="zh-Hans"),
            "overview": FieldRule(order=("bangumi", "douban", "tmdb"), locale="zh-Hans"),
            "poster": FieldRule(order=("tmdb", "bangumi", "douban")),
            "backdrop": FieldRule(order=("tmdb", "bangumi")),
            "release_date": FieldRule(order=("tmdb", "bangumi")),
            "genres": FieldRule(order=("bangumi", "tmdb", "douban"), merge="union"),
            "credits": FieldRule(order=("bangumi", "tmdb", "douban"), merge="union_by_name"),
            "ratings": FieldRule(order=("bangumi", "tmdb", "douban"), merge="namespaced"),
        },
    ),
}

DEFAULT_POLICY_KEY = "tmdb_primary"

# 订阅锚点来源 → 默认策略（ADR-025 §6.4）
ANCHOR_POLICY: dict[str, str] = {
    "douban": "douban_primary",
    "tmdb": "tmdb_primary",
    "bangumi": "bangumi_primary",
}


def get_preset(name: str) -> MetadataPolicy:
    """按名称取得预设策略；支持 provider_only:<key>."""
    if name.startswith("provider_only:"):
        provider = name.split(":", 1)[1]
        if not provider:
            raise ValueError("provider_only 缺少 provider key")
        return MetadataPolicy(key=name, primary=provider)
    policy = _PRESETS.get(name)
    if policy is None:
        raise ValueError(f"未知元数据策略: {name}")
    return policy


def resolve_policy(
    explicit: MetadataPolicy | str | None,
    *,
    anchor_provider: str | None = None,
    system_default: str = DEFAULT_POLICY_KEY,
) -> MetadataPolicy:
    """策略解析顺序：显式设置 > 锚点来源默认 > 系统默认."""
    if isinstance(explicit, MetadataPolicy):
        return explicit
    if explicit:
        return get_preset(explicit)
    if anchor_provider and anchor_provider in ANCHOR_POLICY:
        return get_preset(ANCHOR_POLICY[anchor_provider])
    return get_preset(system_default)

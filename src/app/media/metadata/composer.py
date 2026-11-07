"""字段级元数据合成器.

只做纯函数式合并：输入多个 provider 记录与策略，输出规范快照。
不发起网络请求、不访问数据库。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Collection, Mapping
from datetime import datetime, timezone
from typing import Any

from app.domain.media_types import ProviderMediaType

from .models import (
    Credit,
    EpisodeRecord,
    FieldValue,
    ImageAsset,
    MediaMetadata,
    ProviderCapability,
    ProviderRecord,
    ProviderRef,
    SeasonRecord,
    SourceTier,
)
from .policy import MetadataPolicy

_SCALAR_FIELDS: dict[str, str] = {
    "title": "title",
    "original_title": "original_title",
    "year": "year",
    "release_date": "release_date",
    "runtime": "runtime",
    "overview": "overview",
    "tagline": "tagline",
    "original_language": "original_language",
}

_ARRAY_FIELDS = (
    "aliases",
    "genres",
    "tags",
    "countries",
    "spoken_languages",
    "studios",
    "labels",
    "series",
)

_IMAGE_TYPES = ("poster", "backdrop", "logo", "thumb", "fanart")

_CONFLICT_FIELDS = ("title", "year", "release_date", "runtime")

CapabilityMap = Mapping[str, Collection[ProviderCapability | str]]


class MetadataComposer:
    """按策略合成多个 provider 的规范化记录."""

    def compose(
        self,
        identity_id: str,
        records: list[ProviderRecord],
        policy: MetadataPolicy,
        *,
        content_profile: str = "default",
        scope: str = "default",
        media_type: ProviderMediaType | None = None,
        capabilities: CapabilityMap | None = None,
        locked: dict[str, FieldValue] | None = None,
    ) -> MediaMetadata:
        ordered = _ordered_records(records, policy)
        locked = locked or {}

        fields: dict[str, FieldValue] = {}
        for field_name, attr in _SCALAR_FIELDS.items():
            picked = _pick_scalar(ordered, policy, field_name, attr, capabilities)
            if picked is not None:
                fields[field_name] = picked

        for field_name, value in locked.items():
            if field_name in _SCALAR_FIELDS:
                fields[field_name] = value

        arrays = {name: _merge_array(ordered, policy, name, capabilities) for name in _ARRAY_FIELDS}
        ratings = _merge_ratings(ordered, policy, capabilities)
        images = _merge_images(ordered, policy, capabilities)
        credits = _merge_credits(ordered, policy, capabilities)
        seasons = _pick_seasons(ordered, policy, capabilities)
        episodes = _pick_episodes(ordered, policy, capabilities)
        refs = _merge_refs(ordered)

        resolved_type = media_type or next(
            (record.media_type for record in ordered if record.media_type != ProviderMediaType.UNKNOWN),
            ProviderMediaType.UNKNOWN,
        )
        extra = _merge_extra(ordered)
        conflicts = _detect_conflicts(ordered)
        if conflicts:
            extra["conflicts"] = conflicts

        fetched_at = max((record.fetched_at for record in ordered), default=datetime.now(timezone.utc))
        snapshot = MediaMetadata(
            identity_id=identity_id,
            media_type=resolved_type,
            content_profile=content_profile,
            scope=scope,
            primary_provider=policy.primary,
            refs=refs,
            fields=fields,
            ratings=ratings,
            aliases=arrays["aliases"],
            genres=arrays["genres"],
            tags=arrays["tags"],
            countries=arrays["countries"],
            spoken_languages=arrays["spoken_languages"],
            studios=arrays["studios"],
            labels=arrays["labels"],
            series=arrays["series"],
            credits=credits,
            seasons=seasons,
            episodes=episodes,
            images=images,
            extra=extra,
            fetched_at=fetched_at,
        )
        snapshot.snapshot_hash = _snapshot_hash(snapshot)
        return snapshot


def _ordered_records(records: list[ProviderRecord], policy: MetadataPolicy) -> list[ProviderRecord]:
    order = {provider: index for index, provider in enumerate(policy.provider_order)}
    indexed = list(enumerate(records))
    indexed.sort(key=lambda item: (order.get(item[1].provider, len(order)), item[0]))
    seen: set[tuple[str, str]] = set()
    result: list[ProviderRecord] = []
    for _, record in indexed:
        key = (record.provider, record.external_id)
        if key in seen:
            continue
        seen.add(key)
        result.append(record)
    return result


def _supports(
    provider: str,
    capability: ProviderCapability,
    capabilities: CapabilityMap | None,
) -> bool:
    if capabilities is None:
        return True
    caps = capabilities.get(provider)
    if caps is None:
        return True
    return capability in caps or capability.value in caps


def _candidates(
    records: list[ProviderRecord],
    order: tuple[str, ...],
    capability: ProviderCapability,
    capabilities: CapabilityMap | None,
) -> list[ProviderRecord]:
    position = {provider: index for index, provider in enumerate(order)}
    selected = [
        record
        for record in records
        if record.provider in position and _supports(record.provider, capability, capabilities)
    ]
    selected.sort(
        key=lambda record: (
            position[record.provider],
            _tier_rank(record.source_tier),
        )
    )
    return selected


def _tier_rank(tier: SourceTier | None) -> int:
    return {"api": 0, "html": 1, "scraping": 2}.get(str(tier or ""), 9)


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _pick_scalar(
    records: list[ProviderRecord],
    policy: MetadataPolicy,
    field_name: str,
    attr: str,
    capabilities: CapabilityMap | None,
) -> FieldValue | None:
    order = policy.order_for(field_name)
    candidates = _candidates(records, order, ProviderCapability.DETAIL, capabilities)
    wanted_locale = policy.locale_for(field_name)
    grouped: dict[str, list[ProviderRecord]] = {}
    for record in candidates:
        grouped.setdefault(record.provider, []).append(record)

    # 先按 provider 顺序，再在同一个 provider 内做 locale 优先
    for provider in order:
        group = grouped.get(provider)
        if not group:
            continue
        preferred = [record for record in group if wanted_locale and _locale_matches(record.locale, wanted_locale)]
        preferred = preferred or [record for record in group if record.locale is None] or group
        for record in preferred:
            value = getattr(record, attr)
            if _is_empty(value):
                continue
            return FieldValue(
                value=value,
                provider=record.provider,
                external_id=record.external_id,
                confidence=_ref_confidence(record),
                locale=record.locale,
                fetched_at=record.fetched_at,
            )
    return None


def _locale_matches(record_locale: str | None, wanted: str) -> bool:
    if not record_locale:
        return False
    left = record_locale.lower().replace("_", "-")
    right = wanted.lower().replace("_", "-")
    if left == right:
        return True
    return left.split("-")[0] == right.split("-")[0]


def _ref_confidence(record: ProviderRecord) -> float:
    for ref in record.refs:
        if ref.provider == record.provider and ref.external_id == record.external_id:
            return ref.confidence
    return 1.0


def _merge_array(
    records: list[ProviderRecord],
    policy: MetadataPolicy,
    field_name: str,
    capabilities: CapabilityMap | None,
) -> list[str]:
    candidates = _candidates(records, policy.order_for(field_name), ProviderCapability.DETAIL, capabilities)
    if policy.merge_for(field_name) == "primary_only":
        for record in candidates:
            values = getattr(record, field_name)
            if values:
                return list(values)
        return []
    result: list[str] = []
    seen: set[str] = set()
    for record in candidates:
        for value in getattr(record, field_name):
            key = str(value).strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            result.append(value)
    return result


def _merge_ratings(
    records: list[ProviderRecord],
    policy: MetadataPolicy,
    capabilities: CapabilityMap | None,
) -> dict[str, float]:
    order = policy.order_for("ratings")
    candidates = _candidates(records, order, ProviderCapability.DETAIL, capabilities)
    ratings: dict[str, float] = {}
    for record in candidates:
        for provider, score in record.ratings.items():
            ratings.setdefault(provider, score)
        if record.ratings:
            continue
        direct = record.extra.get("rating")
        if isinstance(direct, (int, float)):
            ratings.setdefault(record.provider, float(direct))
    return ratings


def _merge_images(
    records: list[ProviderRecord],
    policy: MetadataPolicy,
    capabilities: CapabilityMap | None,
) -> dict[str, list[ImageAsset]]:
    result: dict[str, list[ImageAsset]] = {}
    for image_type in _IMAGE_TYPES:
        candidates = _candidates(records, policy.order_for(image_type), ProviderCapability.IMAGES, capabilities)
        assets: list[ImageAsset] = []
        for record in candidates:
            for asset in record.images.get(image_type) or []:
                assets.append(asset if asset.provider else asset.model_copy(update={"provider": record.provider}))
        if assets:
            result[image_type] = assets
    return result


def _merge_credits(
    records: list[ProviderRecord],
    policy: MetadataPolicy,
    capabilities: CapabilityMap | None,
) -> list[Credit]:
    field_name = "credits"
    candidates = _candidates(records, policy.order_for(field_name), ProviderCapability.CREDITS, capabilities)
    if policy.merge_for(field_name) == "primary_only":
        for record in candidates:
            if record.credits:
                return [_credit_with_provider(credit, record.provider) for credit in record.credits]
        return []
    result: list[Credit] = []
    seen: set[tuple[str, str]] = set()
    for record in candidates:
        for credit in record.credits:
            key = (credit.name.strip().lower(), credit.role)
            if not key[0] or key in seen:
                continue
            seen.add(key)
            result.append(_credit_with_provider(credit, record.provider))
    return result


def _credit_with_provider(credit: Credit, provider: str) -> Credit:
    if credit.provider:
        return credit
    return credit.model_copy(update={"provider": provider})


def _pick_seasons(
    records: list[ProviderRecord],
    policy: MetadataPolicy,
    capabilities: CapabilityMap | None,
) -> list[SeasonRecord]:
    return _pick_collection(records, policy, ProviderCapability.SEASONS, "seasons", capabilities)


def _pick_episodes(
    records: list[ProviderRecord],
    policy: MetadataPolicy,
    capabilities: CapabilityMap | None,
) -> list[EpisodeRecord]:
    return _pick_collection(records, policy, ProviderCapability.EPISODES, "episodes", capabilities)


def _pick_collection(
    records: list[ProviderRecord],
    policy: MetadataPolicy,
    capability: ProviderCapability,
    field_name: str,
    capabilities: CapabilityMap | None,
) -> list[Any]:
    candidates = _candidates(records, policy.provider_order, capability, capabilities)
    for record in candidates:
        values = getattr(record, field_name)
        if values:
            return list(values)
    return []


def _merge_refs(records: list[ProviderRecord]) -> list[ProviderRef]:
    result: list[ProviderRef] = []
    seen: set[tuple[str, str, str]] = set()
    for record in records:
        refs = list(record.refs)
        if not any(ref.provider == record.provider and ref.external_id == record.external_id for ref in refs):
            refs.append(
                ProviderRef(
                    provider=record.provider,
                    external_id=record.external_id,
                    media_type=record.media_type,
                    confidence=_ref_confidence(record),
                )
            )
        for ref in refs:
            key = (ref.provider, ref.external_id, ref.scope)
            if key in seen:
                continue
            seen.add(key)
            result.append(ref)
    return result


def _merge_extra(records: list[ProviderRecord]) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    for record in records:
        for key, value in record.extra.items():
            namespaced = key if "." in key else f"{record.provider}.{key}"
            if namespaced not in extra:
                extra[namespaced] = value
    return extra


def _detect_conflicts(records: list[ProviderRecord]) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    for field_name in _CONFLICT_FIELDS:
        values: dict[str, Any] = {}
        for record in records:
            value = getattr(record, field_name)
            if _is_empty(value):
                continue
            values[record.provider] = value
        distinct = {json.dumps(value, ensure_ascii=False, default=str) for value in values.values()}
        if len(distinct) > 1:
            if field_name == "title" and _titles_compatible(values.values()):
                continue
            conflicts.append({"field": field_name, "values": values})
    return conflicts


def _titles_compatible(values) -> bool:
    """季标题 vs 主标题（包含关系）不算冲突."""
    normalized = [re.sub(r"[\s·:：\-—_()（）]", "", str(value)).lower() for value in values]
    return any(left in right or right in left for left in normalized for right in normalized)


def _snapshot_hash(snapshot: MediaMetadata) -> str:
    payload = snapshot.model_dump(
        mode="json",
        exclude={"snapshot_hash", "fetched_at"},
    )
    # fields 内的 fetched_at 属于抓取时间，不参与内容 hash
    for field_value in payload.get("fields", {}).values():
        field_value.pop("fetched_at", None)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

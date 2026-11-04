"""Bangumi 原始条目 → ProviderRecord."""

from __future__ import annotations

import re
from typing import Any, Protocol

from app.domain.mediatypes import MediaType
from app.media.external.bangumi import Bangumi

from ..errors import ProviderNotFound
from ..models import (
    Credit,
    EpisodeRecord,
    ImageAsset,
    ProviderCapability,
    ProviderDescriptor,
    ProviderHealth,
    ProviderRecord,
    ProviderRef,
    SearchHit,
    SearchQuery,
    SeasonRecord,
    SourceTier,
)


class _BangumiClientLike(Protocol):
    def detail(self, bid: str) -> dict[str, Any]: ...

    def search(self, keyword: str, page: int = 1, limit: int = 20, subject_type: int = 2) -> list[Any]: ...


def bangumi_item_to_record(
    item: dict[str, Any],
    *,
    media_type: MediaType = MediaType.ANIME,
    external_id: str | None = None,
    content_profile: str = "anime",
) -> ProviderRecord:
    """把 Bangumi v0 subject / calendar item 映射为规范记录."""
    bid = str(external_id or item.get("id") or "")
    images = item.get("images") or {}
    rating = item.get("rating") or {}
    air_date = item.get("date") or item.get("air_date")
    tags = item.get("tags") or []
    score = rating.get("score")
    infobox = item.get("infobox") or []

    studios: list[str] = []
    aliases: list[str] = []
    credits: list[Credit] = []
    role_map = {
        "导演": "director",
        "脚本": "writer",
        "系列构成": "writer",
        "原作": "writer",
        "人物设定": "writer",
        "音乐": "music",
        "动画制作": "studio",
        "製作": "studio",
        "制作": "studio",
    }
    for info in infobox:
        key = str(info.get("key") or "")
        value = info.get("value")
        if key in {"动画制作", "製作", "制作"} and isinstance(value, str) and value:
            studios.append(value)
        if key == "别名":
            aliases.extend(_infobox_names(value))
        role = role_map.get(key)
        if role == "studio" and isinstance(value, str) and value.strip():
            credits.append(Credit(name=value.strip(), role="studio", provider="bangumi"))
        elif role:
            for name in _infobox_names(value):
                credits.append(Credit(name=name, role=role, provider="bangumi"))
    runtime_match = re.search(r"(\d+)", str(_infobox_value(infobox, "单集片长") or ""))
    runtime = int(runtime_match.group(1)) if runtime_match else None

    return ProviderRecord(
        provider="bangumi",
        external_id=bid,
        refs=[ProviderRef(provider="bangumi", external_id=bid, media_type=media_type)],
        media_type=media_type,
        content_profile=content_profile,
        locale="zh-CN",
        title=item.get("name_cn") or item.get("name") or None,
        original_title=item.get("name") or None,
        year=str(air_date)[:4] if air_date else None,
        release_date=str(air_date) if air_date else None,
        overview=item.get("summary") or None,
        studios=studios,
        aliases=aliases,
        credits=credits,
        runtime=runtime,
        countries=["日本"],
        spoken_languages=["日语"],
        tags=[tag.get("name") for tag in tags if tag.get("name")],
        genres=[
            str(tag.get("name"))
            for tag in tags
            if tag.get("name") and str(tag.get("name")) in {"科幻", "奇幻", "冒险", "动画", "战斗", "剧情"}
        ],
        ratings={"bangumi": float(score)} if isinstance(score, (int, float)) and score else {},
        images={"poster": [ImageAsset(type="poster", url=images["large"], provider="bangumi")]}
        if images.get("large")
        else {},
        extra={
            "bangumi.rank": rating.get("rank"),
            "bangumi.total": rating.get("total"),
            "bangumi.eps": item.get("eps") or item.get("total_episodes"),
            "bangumi.platform": item.get("platform"),
        },
    )


def _runtime_minutes(value: Any) -> int | None:
    """Bangumi 时长可能是 HH:MM:SS 字符串或秒数，统一转分钟."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if ":" in text:
        parts = [int(part) for part in text.split(":") if part.isdigit()]
        if len(parts) >= 2:
            return parts[0] * 60 + parts[1]
        return None
    match = re.search(r"\d+", text)
    return int(match.group(0)) if match else None


def _infobox_value(infobox: list[dict[str, Any]], key: str) -> Any:
    for info in infobox:
        if info.get("key") == key:
            return info.get("value")
    return None


def _infobox_names(value: Any) -> list[str]:
    if isinstance(value, str):
        parts = re.split(r"[、,，/\n]", value)
        return [part.strip() for part in parts if part.strip()]
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            if isinstance(item, dict):
                name = item.get("v") or item.get("name")
                if name:
                    result.append(str(name))
            elif item:
                result.append(str(item))
        return result
    return []


HOSTS = {"api.bgm.tv"}
RATE = 30


class BangumiProvider:
    """Bangumi provider adapter（v0 subject detail）."""

    descriptor = ProviderDescriptor(
        provider_key="bangumi",
        subscription_order=3,
        default_subscription_policy="bangumi_primary",
        display_name="Bangumi",
        ref_prefixes=frozenset({"BG", "BGM", "BANGUMI"}),
        subscription_id_format="BG:{id}",
        default_media_type=MediaType.TV,
        default_content_profile="anime",
        detail_url_template="https://bgm.tv/subject/{external_id}",
        capabilities=frozenset(
            {
                ProviderCapability.SEARCH,
                ProviderCapability.DETAIL,
                ProviderCapability.IMAGES,
                ProviderCapability.CREDITS,
                ProviderCapability.EPISODES,
                ProviderCapability.DISCOVERY,
            }
        ),
        media_types=frozenset({MediaType.ANIME, MediaType.TV}),
        content_profiles=frozenset({"anime"}),
        source_tiers=frozenset({SourceTier.API}),
        allowed_hosts=frozenset(HOSTS),
        rate_limit_per_minute=RATE,
    )

    def __init__(self, client: _BangumiClientLike | None = None) -> None:
        self._client = client or Bangumi()

    def search(self, query: SearchQuery, ctx: object) -> list[SearchHit]:
        raw = self._client.search(query.query, limit=query.limit)
        hits: list[SearchHit] = []
        for item in raw or []:
            bid = item.get("id")
            if not bid:
                continue
            images = item.get("images") or {}
            rating = item.get("rating") or {}
            air_date = item.get("date") or ""
            hits.append(
                SearchHit(
                    provider="bangumi",
                    ref=ProviderRef(provider="bangumi", external_id=str(bid), media_type=MediaType.ANIME),
                    title=item.get("name_cn") or item.get("name") or "",
                    year=str(air_date)[:4] or None,
                    media_type=MediaType.ANIME,
                    content_profile="anime",
                    poster=images.get("large") or images.get("common"),
                    score=float(rating.get("score") or 0.0),
                    extra={"rating": rating.get("score")} if rating.get("score") else {},
                )
            )
        return hits

    def detail(self, ref: ProviderRef, ctx: object) -> ProviderRecord | None:
        info = self._client.detail(ref.external_id)
        if not info or not info.get("id"):
            raise ProviderNotFound("bangumi", f"未找到 {ref.external_id}")
        return bangumi_item_to_record(info, external_id=ref.external_id)

    def map_ids(self, ref: ProviderRef, ctx: object) -> list[ProviderRef]:
        return [ref]

    def seasons(self, ref: ProviderRef, ctx: object) -> list[SeasonRecord]:
        return []

    def episodes(self, ref: ProviderRef, season: int, ctx: object) -> list[EpisodeRecord]:
        client = self._client
        getter = getattr(client, "episodes", None)
        if getter is None:
            return []
        try:
            raw = getter(ref.external_id)
        except Exception:  # noqa: BLE001 - 分集失败不影响详情
            return []
        result: list[EpisodeRecord] = []
        for item in raw or []:
            number = item.get("ep") or item.get("sort")
            if number is None:
                continue
            duration_seconds = item.get("duration_seconds")
            runtime = (
                int(duration_seconds) // 60
                if duration_seconds not in (None, "")
                else _runtime_minutes(item.get("duration"))
            )
            result.append(
                EpisodeRecord(
                    season_number=season or 1,
                    episode_number=int(number),
                    title=item.get("name_cn") or item.get("name"),
                    overview=item.get("desc"),
                    air_date=item.get("airdate") or item.get("air_date"),
                    runtime=runtime,
                )
            )
        return result

    def health(self, ctx: object) -> ProviderHealth:
        return ProviderHealth(provider="bangumi", ok=True)

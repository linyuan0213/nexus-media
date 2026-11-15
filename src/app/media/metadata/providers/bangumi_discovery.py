"""Bangumi 探索页：放送日历、当季新番与国家识别."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, cast

from app.domain.media_types import ProviderMediaType
from app.media.external.bangumi import Bangumi

from ..models import (
    DiscoveryFeed,
    DiscoveryItem,
    DiscoveryPage,
    ProviderCapability,
    ProviderDescriptor,
    ProviderRef,
)
from .discovery import (
    FeedKind,
    _country_filter,
    _country_from_values,
    _country_options,
    _genre_facets,
    current_season,
    season_range,
)


class BangumiDiscovery:
    """Bangumi 放送日历与当季新番."""

    descriptor = ProviderDescriptor(
        provider_key="bangumi",
        display_name="Bangumi",
        capabilities=frozenset({ProviderCapability.DISCOVERY}),
        content_profiles=frozenset({"anime"}),
        visibility="public",
    )

    _FEEDS: dict[str, tuple[str, FeedKind, bool]] = {
        "calendar": ("放送日历", "calendar", False),
        "seasonal": ("每季新番", "seasonal", True),
    }

    def __init__(self, client: Any | None = None) -> None:
        self._client = client or Bangumi()
        self._country_cache: dict[str, list[str]] = {}

    def _detail_country(self, external_id: str) -> list[str]:
        cached = self._country_cache.get(external_id)
        if cached is not None:
            return cached
        detail_fn = getattr(self._client, "detail", None)
        if not callable(detail_fn):
            return []
        try:
            detail = cast(dict[str, Any], detail_fn(external_id) or {})
        except Exception:
            return []
        tag_counts = {
            str(tag.get("name") or ""): int(tag.get("count") or 1)
            for tag in (detail.get("tags") or [])
            if isinstance(tag, dict)
        }
        meta_tags = {str(tag) for tag in detail.get("meta_tags") or []}
        if "日本" in meta_tags:
            country = ["日本"]
        else:
            jp_count = tag_counts.get("日本", 0) + tag_counts.get("日本动画", 0)
            cn_count = sum(tag_counts.get(tag, 0) for tag in ("国产", "国漫", "中国", "中国动画", "中国动画片"))
            # 个别条目会被人误加“国产”标签，优先看主流国家标签数量。
            if jp_count and jp_count >= cn_count:
                country = ["日本"]
            elif cn_count:
                country = ["中国"]
            else:
                country = _country_from_values(sorted(tag_counts))
        self._country_cache[external_id] = country
        return country

    def _enrich_countries(self, items: list[DiscoveryItem]) -> None:
        pending = [item for item in items if not item.countries and item.ref.external_id]
        if not pending:
            return
        with ThreadPoolExecutor(max_workers=8) as pool:
            countries = list(pool.map(lambda item: self._detail_country(item.ref.external_id), pending))
        for item, country in zip(pending, countries, strict=False):
            item.countries = country

    def feeds(self, ctx: object) -> list[DiscoveryFeed]:
        return [
            DiscoveryFeed(
                key=key,
                title=title,
                kind=kind,
                facets=(
                    ["season", "year", "genre", "country"]
                    if seasonal
                    else ["weekday", "year", "country"]
                    if kind == "calendar"
                    else ["year", "country"]
                ),
            )
            for key, (title, kind, seasonal) in self._FEEDS.items()
        ]

    def items(self, feed: str, page: int, filters: dict, ctx: object) -> DiscoveryPage:
        if feed not in self._FEEDS:
            return DiscoveryPage(items=[], page=page)
        start, end = season_range(str(filters.get("season") or current_season()))
        items: list[DiscoveryItem] = []
        has_more = False
        search_season: Any = getattr(self._client, "search_season", None)
        if feed == "seasonal" and callable(search_season):
            search_fn: Any = search_season
            country_filter = str(filters.get("country") or "").strip()
            if country_filter:
                # 国家筛选需要覆盖整季全量列表，不能只取当前页。
                offset_page = 1
                while offset_page <= 25:
                    raw_items, total = search_fn(start, end, page=offset_page, limit=20)
                    for source in raw_items:
                        item = _bangumi_discovery_item(source)
                        if item is None:
                            continue
                        year = str(filters.get("year") or "")
                        if year and item.year != year:
                            continue
                        items.append(item)
                    if not raw_items or offset_page * 20 >= total:
                        break
                    offset_page += 1
                has_more = False
            else:
                raw_items, total = search_fn(start, end, page=page, limit=20)
                for source in raw_items:
                    item = _bangumi_discovery_item(source)
                    if item is None:
                        continue
                    year = str(filters.get("year") or "")
                    if year and item.year != year:
                        continue
                    items.append(item)
                has_more = page * 20 < total
        else:
            raw = self._client.calendar() or []
            weekday_filter = str(filters.get("weekday") or "")
            for day in raw:
                day_weekday = str(
                    (day.get("weekday") or {}).get("id")
                    if isinstance(day.get("weekday"), dict)
                    else day.get("weekday") or ""
                )
                if weekday_filter and day_weekday and weekday_filter != day_weekday:
                    continue
                for source in day.get("items") or []:
                    item = _bangumi_discovery_item(source)
                    if item is None:
                        continue
                    air_date = item.extra.get("air_date")
                    if feed == "seasonal" and air_date and not (start <= str(air_date) <= end):
                        continue
                    year = str(filters.get("year") or "")
                    if year and item.year != year:
                        continue
                    items.append(item)
        self._enrich_countries(items)
        mainstream, facets = _genre_facets(items)
        genre = str(filters.get("genre") or "").strip()
        if genre == "其他":
            items = [item for item in items if not any(any(main in tag for tag in item.tags) for main in mainstream)]
        elif genre:
            items = [item for item in items if any(genre in tag for tag in item.tags)]
        items = _country_filter(items, str(filters.get("country") or "").strip())
        return DiscoveryPage(
            items=items,
            page=page,
            has_more=has_more,
            facets={"genre": facets, "country": _country_options()},
        )


def _bangumi_discovery_item(raw: dict[str, Any]) -> DiscoveryItem | None:
    external_id = str(raw.get("id") or "").strip()
    if not external_id:
        return None
    images = raw.get("images") or {}
    rating = raw.get("rating") or {}
    air_date = raw.get("air_date") or raw.get("date")
    return DiscoveryItem(
        provider="bangumi",
        ref=ProviderRef(
            provider="bangumi",
            external_id=external_id,
            provider_media_type=ProviderMediaType.ANIME,
        ),
        content_profile="anime",
        title=str(raw.get("name_cn") or raw.get("name") or ""),
        original_title=raw.get("name"),
        year=str(air_date)[:4] if air_date else None,
        poster=images.get("large") or images.get("common"),
        rating={"bangumi": float(rating["score"])} if rating.get("score") else {},
        tags=[str(tag.get("name")) for tag in raw.get("tags") or [] if tag.get("name")],
        countries=_country_from_values([tag.get("name") for tag in raw.get("tags") or [] if isinstance(tag, dict)]),
        anchor_ref=ProviderRef(
            provider="bangumi",
            external_id=external_id,
            provider_media_type=ProviderMediaType.ANIME,
        ),
        actions=["subscribe", "detail"],
        extra={"air_date": air_date, "bangumi.rank": rating.get("rank")},
    )

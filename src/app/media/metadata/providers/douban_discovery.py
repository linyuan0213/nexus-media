"""豆瓣探索页：榜单/热门 feed."""

from __future__ import annotations

from typing import Any

from app.domain.media_types import ProviderMediaType, provider_media_type_of
from app.infrastructure.external.doubanapi.apiv2 import DoubanApi

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
)
from .genres import classify_provider_media_type


class DoubanDiscovery:
    """豆瓣榜单/热门 feed."""

    descriptor = ProviderDescriptor(
        provider_key="douban",
        display_name="豆瓣",
        capabilities=frozenset({ProviderCapability.DISCOVERY}),
        visibility="public",
    )

    _FEEDS: dict[str, tuple[str, FeedKind]] = {
        "movie_showing": ("正在热映", "ranking"),
        "movie_hot_gaia": ("热门电影", "trending"),
        "movie_soon": ("即将上映", "latest"),
        "movie_top250": ("豆瓣 Top250", "ranking"),
        "tv_hot": ("热门剧集", "trending"),
        "tv_chinese_best_weekly": ("华语口碑周榜", "ranking"),
        "tv_global_best_weekly": ("全球口碑周榜", "ranking"),
        "tv_animation": ("热门动画", "trending"),
        "tv_variety_show": ("热门综艺", "trending"),
    }

    def __init__(self, api: Any | None = None) -> None:
        self._api = api or DoubanApi()

    def feeds(self, ctx: object) -> list[DiscoveryFeed]:
        return [
            DiscoveryFeed(key=key, title=title, kind=kind, facets=["year", "genre", "country"])
            for key, (title, kind) in self._FEEDS.items()
        ]

    def items(self, feed: str, page: int, filters: dict, ctx: object) -> DiscoveryPage:
        if feed not in self._FEEDS:
            return DiscoveryPage(items=[], page=page)
        count = 50
        start = max(0, (page - 1) * count)
        method = getattr(self._api, feed)
        active_filters = any(str(filters.get(key) or "").strip() for key in ("year", "genre", "country"))
        source_items: list[dict] = []
        total = 0
        if active_filters:
            # 筛选必须基于榜单全量数据，不能只过滤当前页。
            offset = 0
            while offset < 500:
                chunk = method(start=offset, count=count) or {}
                batch = chunk.get("subject_collection_items") or []
                total = int(chunk.get("total") or total or len(batch))
                source_items.extend(batch)
                if not batch or len(source_items) >= total or len(batch) < count:
                    break
                offset += count
            has_more = False
        else:
            raw = method(start=start, count=count) or {}
            source_items = raw.get("subject_collection_items") or []
            total = int(raw.get("total") or len(source_items))
            has_more = start + count < total
        year = str(filters.get("year") or "")
        content_profile = "anime" if feed == "tv_animation" else "default"
        items = [
            item
            for raw_item in source_items
            if (
                item := _douban_discovery_item(
                    raw_item,
                    content_profile=content_profile,
                    genres=raw_item.get("genres") or raw_item.get("tags") or [],
                )
            )
            is not None
            and (not year or item.year == year)
        ]
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


def _douban_discovery_item(
    raw: dict[str, Any],
    *,
    content_profile: str = "default",
    genres: list[Any] | None = None,
) -> DiscoveryItem | None:
    external_id = str(raw.get("id") or "").strip()
    if not external_id:
        return None
    cover = raw.get("cover_url")
    if not cover and isinstance(raw.get("cover"), dict):
        cover = raw["cover"].get("url")
    # 豆瓣榜单的 photos[0] 多为 540x303 剧照，真正的 2:3 主海报在 pic.large。
    if not cover:
        pic = raw.get("pic") or {}
        if isinstance(pic, dict):
            cover = pic.get("large") or pic.get("normal")
    if not cover:
        photos = raw.get("photos") or []
        cover = photos[0] if photos else None
    provider_type = provider_media_type_of(raw.get("type"))
    if provider_type == ProviderMediaType.UNKNOWN and raw.get("episodes_info"):
        provider_type = ProviderMediaType.SERIES
    _, content_profile = classify_provider_media_type(provider_type, genres, content_profile)
    rating = raw.get("rating") or {}
    year = str(raw.get("year") or "")
    card = str(raw.get("card_subtitle") or "")
    if not year:
        year = card[:4] if card[:4].isdigit() else ""
    card_parts = [part.strip() for part in card.split("/") if part.strip()]
    genres = []
    if len(card_parts) > 2:
        candidate = card_parts[2]
        if "·" not in candidate and " " not in candidate and len(candidate) <= 6:
            genres.append(candidate)
    return DiscoveryItem(
        provider="douban",
        ref=ProviderRef(
            provider="douban",
            external_id=external_id,
            provider_media_type=provider_type,
        ),
        content_profile=content_profile,
        title=str(raw.get("title") or ""),
        year=year or None,
        poster=cover,
        rating={"douban": float(rating["value"])} if rating.get("value") is not None else {},
        tags=genres or [str(tag) for tag in raw.get("tags") or [] if tag],
        countries=_country_from_values([raw.get("card_subtitle"), *(raw.get("tags") or [])]),
        anchor_ref=ProviderRef(
            provider="douban",
            external_id=external_id,
            provider_media_type=provider_type,
        ),
        actions=["subscribe", "detail"],
        extra={
            "douban.card_subtitle": raw.get("card_subtitle"),
            "douban.rank": raw.get("rank"),
            "douban.episodes_info": raw.get("episodes_info"),
        },
    )

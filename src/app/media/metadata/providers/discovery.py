"""发现（探索页）来源适配器与季度工具."""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any, Literal

import log
from app.domain.media_types import ProviderMediaType, provider_media_type_of
from app.domain.mediatypes import MediaType
from app.infrastructure.external.doubanapi.apiv2 import DoubanApi
from app.infrastructure.image_proxy import ImageProxy
from app.media.external.bangumi import Bangumi

from ..models import (
    DiscoveryFeed,
    DiscoveryItem,
    DiscoveryPage,
    FacetValue,
    ProviderCapability,
    ProviderDescriptor,
    ProviderRef,
)
from .genres import classify_provider_media_type

FeedKind = Literal["ranking", "trending", "latest", "calendar", "seasonal", "collection", "search"]


def season_range(season: str | None, *, today: date | None = None) -> tuple[str, str]:
    """把 2026-winter / 2026-q1 转为日期区间；缺省为当前季度."""
    current = today or date.today()
    year = current.year
    key = (season or "").strip().lower()
    if "-" in key:
        raw_year, raw_key = key.split("-", 1)
        if raw_year.isdigit():
            year = int(raw_year)
            key = raw_key
    mapping = {
        "winter": (1, 1, 3, 31),
        "spring": (4, 1, 6, 30),
        "summer": (7, 1, 9, 30),
        "fall": (10, 1, 12, 31),
        "autumn": (10, 1, 12, 31),
        "q1": (1, 1, 3, 31),
        "q2": (4, 1, 6, 30),
        "q3": (7, 1, 9, 30),
        "q4": (10, 1, 12, 31),
    }
    if key not in mapping:
        month = current.month
        key = "q1" if month <= 3 else "q2" if month <= 6 else "q3" if month <= 9 else "q4"
    start_month, start_day, end_month, end_day = mapping[key]
    return (
        date(year, start_month, start_day).isoformat(),
        date(year, end_month, end_day).isoformat(),
    )


def current_season(today: date | None = None) -> str:
    current = today or date.today()
    quarter = (current.month - 1) // 3 + 1
    return f"{current.year}-q{quarter}"


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
            DiscoveryFeed(key=key, title=title, kind=kind, facets=["year", "genre"])
            for key, (title, kind) in self._FEEDS.items()
        ]

    def items(self, feed: str, page: int, filters: dict, ctx: object) -> DiscoveryPage:
        if feed not in self._FEEDS:
            return DiscoveryPage(items=[], page=page)
        count = 50
        start = max(0, (page - 1) * count)
        method = getattr(self._api, feed)
        raw = method(start=start, count=count) or {}
        year = str(filters.get("year") or "")
        content_profile = "anime" if feed == "tv_animation" else "default"
        items = [
            item
            for raw_item in raw.get("subject_collection_items") or []
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
        total = int(raw.get("total") or len(items))
        return DiscoveryPage(
            items=items,
            page=page,
            has_more=start + count < total,
            facets={"genre": facets},
        )


class TmdbDiscovery:
    """TMDB 趋势/热门/季度档 feed."""

    descriptor = ProviderDescriptor(
        provider_key="tmdb",
        display_name="TMDB",
        capabilities=frozenset({ProviderCapability.DISCOVERY}),
        visibility="public",
    )

    _FEEDS: dict[str, tuple[str, FeedKind, bool]] = {
        "trending": ("趋势", "trending", False),
        "popular_movies": ("热门电影", "trending", False),
        "popular_tvs": ("热门剧集", "trending", False),
        "seasonal_tv": ("季度新剧", "seasonal", True),
        "seasonal_movie": ("季度新片", "seasonal", True),
        "seasonal_anime": ("每季新番", "seasonal", True),
    }

    def __init__(self, media_service: Any) -> None:
        self._media = media_service
        self._genre_maps: dict[str, dict[str, str]] = {}

    def feeds(self, ctx: object) -> list[DiscoveryFeed]:
        feeds = []
        for key, (title, kind, seasonal) in self._FEEDS.items():
            feeds.append(
                DiscoveryFeed(
                    key=key,
                    title=title,
                    kind=kind,
                    facets=["season", "year", "genre"] if seasonal else ["year", "genre"],
                )
            )
        return feeds

    def items(self, feed: str, page: int, filters: dict, ctx: object) -> DiscoveryPage:
        if feed not in self._FEEDS:
            return DiscoveryPage(items=[], page=page)
        if feed == "trending":
            raw = self._media.get_tmdb_trending_all_week(page) or []
        elif feed == "popular_movies":
            raw = self._media.get_tmdb_hot_movies(page) or []
        elif feed == "popular_tvs":
            raw = self._media.get_tmdb_hot_tvs(page) or []
        else:
            raw = self._seasonal(feed, page, filters)
        year = str(filters.get("year") or "")
        items = []
        for source in raw:
            item = _tmdb_discovery_item(source)
            if item is None or (year and item.year != year):
                continue
            if feed == "seasonal_anime":
                item.content_profile = "anime"
            _, item.content_profile = classify_provider_media_type(
                item.ref.provider_media_type or ProviderMediaType.UNKNOWN,
                source.get("genre_ids") or [],
                item.content_profile,
            )
            genre_map = self._tmdb_genre_map(item.ref.provider_media_type)
            item.tags = [
                genre_map[str(genre_id)] for genre_id in source.get("genre_ids") or [] if str(genre_id) in genre_map
            ]
            items.append(item)
        mainstream, facets = _genre_facets(items)
        genre = str(filters.get("genre") or "").strip()
        if genre == "其他":
            items = [item for item in items if not any(any(main in tag for tag in item.tags) for main in mainstream)]
        elif genre:
            items = [item for item in items if any(genre in tag for tag in item.tags)]
        return DiscoveryPage(
            items=items,
            page=page,
            has_more=bool(raw and len(raw) >= 20),
            facets={"genre": facets},
        )

    def _tmdb_genre_map(self, media_type: MediaType | ProviderMediaType | None) -> dict[str, str]:
        provider_type = provider_media_type_of(media_type)
        key = provider_type.value if media_type is not None else "movie"
        if key in self._genre_maps:
            return self._genre_maps[key]
        mapping: dict[str, str] = {}
        raw_genres = []
        try:
            raw_genres = self._media.get_tmdb_genres(provider_type) or []
            for item in raw_genres:
                if isinstance(item, dict):
                    genre_id, genre_name = item.get("id"), item.get("name")
                else:
                    genre_id, genre_name = getattr(item, "id", None), getattr(item, "name", None)
                if genre_id and genre_name:
                    mapping[str(genre_id)] = str(genre_name)
        except Exception as exc:  # noqa: BLE001
            log.warn(f"[Discovery]TMDB题材加载失败: {exc}")
        self._genre_maps[key] = mapping
        return mapping

    def _seasonal(self, feed: str, page: int, filters: dict) -> list[dict]:
        start, end = season_range(str(filters.get("season") or current_season()))
        if feed == "seasonal_movie":
            return (
                self._media.get_tmdb_discover(
                    ProviderMediaType.MOVIE,
                    params={
                        "primary_release_date.gte": start,
                        "primary_release_date.lte": end,
                        "sort_by": "popularity.desc",
                    },
                    page=page,
                )
                or []
            )
        params: dict[str, Any] = {
            "first_air_date.gte": start,
            "first_air_date.lte": end,
            "sort_by": "popularity.desc",
        }
        if feed == "seasonal_anime":
            params["with_genres"] = 16
        return self._media.get_tmdb_discover(ProviderMediaType.SERIES, params=params, page=page) or []


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

    def feeds(self, ctx: object) -> list[DiscoveryFeed]:
        return [
            DiscoveryFeed(
                key=key,
                title=title,
                kind=kind,
                facets=(
                    ["season", "year", "genre"] if seasonal else ["weekday", "year"] if kind == "calendar" else ["year"]
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
        mainstream, facets = _genre_facets(items)
        genre = str(filters.get("genre") or "").strip()
        if genre == "其他":
            items = [item for item in items if not any(any(main in tag for tag in item.tags) for main in mainstream)]
        elif genre:
            items = [item for item in items if any(genre in tag for tag in item.tags)]
        return DiscoveryPage(
            items=items,
            page=page,
            has_more=has_more,
            facets={"genre": facets},
        )


_NON_GENRE_TAGS = {
    "日本",
    "中国",
    "美国",
    "韩国",
    "欧美",
    "TV",
    "TVA",
    "WEB",
    "OVA",
    "剧场版",
    "动画",
    "日本动画",
    "漫画",
    "小说",
    "游戏",
    "原创",
    "续作",
    "未定档",
    "季番",
    "漫改",
    "轻改",
    "小说改",
    "漫画改",
    "游戏改",
    "轻小说改",
}


def _genre_facets(items: list[DiscoveryItem], limit: int = 16) -> tuple[list[str], list[FacetValue]]:
    """从当前页标签动态提取主流题材，其余归入其他."""
    counts = Counter(
        str(tag).strip()
        for item in items
        for tag in item.tags
        if str(tag).strip()
        and str(tag).strip() not in _NON_GENRE_TAGS
        and not any(char.isdigit() for char in str(tag))
        and not str(tag).isascii()
        and len(str(tag)) <= 6
    )
    mainstream = [tag for tag, _count in counts.most_common(limit)]
    tagged = 0
    for item in items:
        if any(any(main in tag for tag in item.tags) for main in mainstream):
            tagged += 1
    facets = [
        FacetValue(
            value=tag,
            label=tag,
            count=sum(1 for item in items if any(tag in value for value in item.tags)),
        )
        for tag in mainstream
    ]
    if tagged < len(items):
        facets.append(FacetValue(value="其他", label="其他", count=len(items) - tagged))
    return mainstream, facets


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


def _tmdb_discovery_item(raw: dict[str, Any]) -> DiscoveryItem | None:
    external_id = str(raw.get("id") or raw.get("tmdbid") or "").strip()
    if not external_id:
        return None
    provider_type = provider_media_type_of(raw.get("media_type") or raw.get("type"))
    vote = raw.get("vote")
    return DiscoveryItem(
        provider="tmdb",
        ref=ProviderRef(
            provider="tmdb",
            external_id=external_id,
            provider_media_type=provider_type,
        ),
        content_profile="default",
        title=str(raw.get("title") or raw.get("name") or ""),
        year=str(raw.get("year") or "") or None,
        poster=raw.get("image") or ImageProxy.get_tmdbimage_url(raw.get("poster_path")),
        rating={"tmdb": float(vote)} if isinstance(vote, (int, float)) and vote else {},
        anchor_ref=ProviderRef(
            provider="tmdb",
            external_id=external_id,
            provider_media_type=provider_type,
        ),
        actions=["subscribe", "detail"],
        extra={"tmdb.genre_ids": raw.get("genre_ids") or []},
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
        anchor_ref=ProviderRef(
            provider="bangumi",
            external_id=external_id,
            provider_media_type=ProviderMediaType.ANIME,
        ),
        actions=["subscribe", "detail"],
        extra={"air_date": air_date, "bangumi.rank": rating.get("rank")},
    )

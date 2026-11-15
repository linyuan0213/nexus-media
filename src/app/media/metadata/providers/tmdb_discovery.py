"""TMDB 探索页：趋势、热门与季度档 feed."""

from __future__ import annotations

from typing import Any

import log
from app.domain.media_types import ProviderMediaType, provider_media_type_of
from app.infrastructure.image_proxy import ImageProxy

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
    _country_from_values,
    _country_options,
    _genre_facets,
    current_season,
    season_range,
)
from .genres import classify_provider_media_type

_LANGUAGE_COUNTRY_LABELS = {
    "ja": "日本",
    "zh": "中国",
    "ko": "韩国",
    "en": "美国",
    "th": "泰国",
    "fr": "法国",
    "de": "德国",
    "es": "西班牙",
}


_COUNTRY_ISO = {
    "中国": "CN",
    "中国香港": "HK",
    "中国台湾": "TW",
    "日本": "JP",
    "韩国": "KR",
    "美国": "US",
    "英国": "GB",
    "法国": "FR",
    "德国": "DE",
    "泰国": "TH",
}


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
                    facets=(["season", "year", "genre", "country"] if seasonal else ["year", "genre", "country"]),
                )
            )
        return feeds

    def items(self, feed: str, page: int, filters: dict, ctx: object) -> DiscoveryPage:
        if feed not in self._FEEDS:
            return DiscoveryPage(items=[], page=page)
        country = str(filters.get("country") or "").strip()
        country_code = _COUNTRY_ISO.get(country)
        if country_code and feed in {"popular_movies", "popular_tvs", "trending"}:
            raw = self._country_discover(feed, page, country_code)
        elif feed == "trending":
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
        # 国家筛选已在 TMDB discover 查询层完成，这里不再按当前页二次过滤。
        return DiscoveryPage(
            items=items,
            page=page,
            has_more=bool(raw and len(raw) >= 20),
            facets={"genre": facets, "country": _country_options()},
        )

    def _country_discover(self, feed: str, page: int, country_code: str) -> list[dict]:
        params: dict[str, Any] = {
            "with_origin_country": country_code,
            "sort_by": "popularity.desc",
        }
        if feed == "popular_movies":
            return self._media.get_tmdb_discover(ProviderMediaType.MOVIE, params=params, page=page) or []
        if feed == "popular_tvs":
            return self._media.get_tmdb_discover(ProviderMediaType.SERIES, params=params, page=page) or []
        movies = self._media.get_tmdb_discover(ProviderMediaType.MOVIE, params=params, page=page) or []
        tvs = self._media.get_tmdb_discover(ProviderMediaType.SERIES, params=params, page=page) or []
        return [*movies, *tvs]

    def _tmdb_genre_map(self, media_type: ProviderMediaType | ProviderMediaType | None) -> dict[str, str]:
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
        country_code = _COUNTRY_ISO.get(str(filters.get("country") or "").strip())
        if country_code:
            params["with_origin_country"] = country_code
        if feed == "seasonal_anime":
            params["with_genres"] = 16
        return self._media.get_tmdb_discover(ProviderMediaType.SERIES, params=params, page=page) or []


def _tmdb_discovery_item(raw: dict[str, Any]) -> DiscoveryItem | None:
    external_id = str(raw.get("id") or raw.get("tmdbid") or "").strip()
    if not external_id:
        return None
    provider_type = provider_media_type_of(raw.get("media_type") or raw.get("type"))
    vote = raw.get("vote")
    countries = _country_from_values(raw.get("origin_country") or raw.get("countries") or [])
    if not countries:
        language_country = _LANGUAGE_COUNTRY_LABELS.get(str(raw.get("original_language") or "").lower())
        if language_country:
            countries = [language_country]
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
        countries=countries,
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

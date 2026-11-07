"""豆瓣详情 → ProviderRecord.

纯映射函数；HTML 分集等能力由后续 adapter 补充。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, Protocol

import log
from app.core.settings import settings
from app.domain.media_types import MediaKind, ProviderMediaType, provider_media_type_of
from app.domain.mediatypes import MediaType
from app.infrastructure.external.doubanapi.apiv2 import DoubanApi
from app.infrastructure.external.doubanapi.episode_queue import episode_queue

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
from .genres import classify_provider_media_type


class _EpisodeScraperLike(Protocol):
    def fetch(self, subject_id: str, season: int = 1) -> Any: ...


class _DoubanApiLike(Protocol):
    def search(self, keyword: str, start: int = 0, count: int = 20, ts: Any = None) -> dict[str, Any]: ...

    def movie_detail(self, subject_id: str) -> dict[str, Any] | None: ...

    def tv_detail(self, subject_id: str) -> dict[str, Any] | None: ...


_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
_RUNTIME_RE = re.compile(r"(\d+)")


def douban_detail_to_record(
    info: dict[str, Any],
    *,
    media_type: MediaType | ProviderMediaType,
    external_id: str | None = None,
    locale: str = "zh-CN",
    content_profile: str = "default",
    seasons: Sequence[SeasonRecord] | None = None,
    episodes: Sequence[EpisodeRecord] | None = None,
) -> ProviderRecord:
    """把豆瓣 frodo detail 字典映射为规范记录."""
    genres = list(info.get("genres") or [])
    provider_type, content_profile = classify_provider_media_type(
        provider_media_type_of(media_type),
        genres,
        content_profile,
    )
    douban_id = str(external_id or info.get("id") or "")
    year = str(info.get("year") or "") or None

    refs = [
        ProviderRef(
            provider="douban",
            external_id=douban_id,
            provider_media_type=provider_type,
        )
    ]
    imdb_id = str(info.get("imdb") or "").strip()
    if imdb_id.startswith("tt"):
        refs.append(
            ProviderRef(
                provider="imdb",
                external_id=imdb_id,
                provider_media_type=provider_type,
            )
        )
    return ProviderRecord(
        provider="douban",
        external_id=douban_id,
        refs=refs,
        media_type=provider_type.to_media_type(),
        provider_media_type=provider_type,
        content_profile=content_profile,
        locale=locale,
        title=info.get("title") or None,
        original_title=info.get("original_title") or None,
        aliases=list(info.get("aka") or []),
        year=year,
        release_date=pick_release_date(info.get("pubdate"), year),
        runtime=parse_runtime(info.get("durations")),
        overview=info.get("intro") or None,
        countries=list(info.get("countries") or []),
        spoken_languages=list(info.get("languages") or []),
        genres=genres,
        ratings=_rating(info),
        images=_images(info),
        credits=_credits(info),
        seasons=list(seasons or []),
        episodes=list(episodes or []),
        extra={
            "douban.comment_count": info.get("comment_count"),
            "douban.review_count": info.get("review_count"),
            "douban.honor_infos": info.get("honor_infos") or [],
            "douban.card_subtitle": info.get("card_subtitle"),
            "douban.is_restrictive": info.get("is_restrictive"),
            "douban.null_rating_reason": info.get("null_rating_reason"),
            "douban.episodes_count": info.get("episodes_count"),
            "douban.imdb": info.get("imdb"),
        },
    )


def pick_release_date(pubdate: Any, year: str | None) -> str | None:
    """从 pubdate 数组取最早的有效上映日.

    豆瓣 pubdate 可能包含地区重映日期（如 1994 年电影返回 2026 年重映），
    超过 year + 3 年的值直接丢弃。
    """
    if not isinstance(pubdate, list):
        return None
    year_number = int(year) if year and year.isdigit() else None
    dates: list[str] = []
    for item in pubdate:
        match = _DATE_RE.match(str(item).strip())
        if not match:
            continue
        candidate = match.group(0)
        if year_number is not None and int(match.group(1)) > year_number + 3:
            continue
        dates.append(candidate)
    return min(dates) if dates else None


def parse_runtime(durations: Any) -> int | None:
    if not isinstance(durations, list):
        return None
    for item in durations:
        match = _RUNTIME_RE.search(str(item))
        if match:
            return int(match.group(1))
    return None


def _infer_provider_type(info: dict[str, Any]) -> ProviderMediaType:
    """仅从详情显式字段/集数推断，未知时保持 UNKNOWN，不默认电影."""
    explicit = provider_media_type_of(info.get("type") or info.get("type_name"))
    if explicit != ProviderMediaType.UNKNOWN:
        return explicit
    if info.get("episodes_count"):
        return ProviderMediaType.SERIES
    return ProviderMediaType.UNKNOWN


def _rating(info: dict[str, Any]) -> dict[str, float]:
    rating = info.get("rating") or {}
    value = rating.get("value")
    if isinstance(value, (int, float)):
        return {"douban": float(value)}
    return {}


def _images(info: dict[str, Any]) -> dict[str, list[ImageAsset]]:
    cover = info.get("cover_url")
    if not cover:
        return {}
    return {"poster": [ImageAsset(type="poster", url=cover, provider="douban")]}


def _credits(info: dict[str, Any]) -> list[Credit]:
    result: list[Credit] = []
    for role, key in (("director", "directors"), ("actor", "actors")):
        for index, member in enumerate(info.get(key) or []):
            name = member.get("name")
            if not name:
                continue
            avatar = member.get("avatar") or {}
            result.append(
                Credit(
                    name=name,
                    role=role,
                    order=index,
                    provider="douban",
                    external_id=str(member.get("id")) if member.get("id") else None,
                    image_url=avatar.get("large") if isinstance(avatar, dict) else None,
                )
            )
    return result


HOSTS = {
    "movie.douban.com",
    "m.douban.com",
    "www.douban.com",
    "img1.doubanio.com",
    "img2.doubanio.com",
    "img3.doubanio.com",
    "img9.doubanio.com",
}
RATE = 20


class DoubanProvider:
    """豆瓣 provider adapter（frodo API；HTML 分集能力后续接入）."""

    descriptor = ProviderDescriptor(
        provider_key="douban",
        subscription_order=2,
        default_subscription_policy="douban_primary",
        display_name="豆瓣",
        ref_prefixes=frozenset({"DB", "DOUBAN"}),
        subscription_id_format="DB:{id}",
        default_provider_media_type=ProviderMediaType.MOVIE,
        detail_url_template="https://movie.douban.com/subject/{external_id}",
        capabilities=frozenset(
            {
                ProviderCapability.SEARCH,
                ProviderCapability.DETAIL,
                ProviderCapability.CREDITS,
                ProviderCapability.IMAGES,
                ProviderCapability.EPISODES,
                ProviderCapability.DISCOVERY,
            }
        ),
        provider_media_types=frozenset({ProviderMediaType.MOVIE, ProviderMediaType.SERIES, ProviderMediaType.ANIME}),
        media_kinds=frozenset({MediaKind.MOVIE, MediaKind.EPISODIC}),
        rate_limit_per_minute=RATE,
        source_tiers=frozenset({SourceTier.API, SourceTier.HTML}),
    )

    def __init__(
        self,
        api: _DoubanApiLike | None = None,
        episode_scraper: _EpisodeScraperLike | None = None,
    ) -> None:
        self._api = api or DoubanApi()
        self._episode_scraper = episode_scraper

    def search(self, query: SearchQuery, ctx: object) -> list[SearchHit]:
        raw = self._api.search(query.query, count=query.limit)
        hits: list[SearchHit] = []
        for item in (raw or {}).get("items") or []:
            target = item.get("target") or {}
            if not target.get("id"):
                continue
            provider_type = provider_media_type_of(item.get("type_name") or target.get("type"))
            target_rating = target.get("rating")
            rating_value = target_rating.get("value") if isinstance(target_rating, dict) else target_rating
            hits.append(
                SearchHit(
                    provider="douban",
                    ref=ProviderRef(
                        provider="douban",
                        external_id=str(target["id"]),
                        provider_media_type=provider_type,
                    ),
                    title=target.get("title") or "",
                    year=str(target.get("year") or "") or None,
                    media_type=provider_type.to_media_type(),
                    content_profile=query.content_profile,
                    poster=target.get("cover_url"),
                    extra={"rating": rating_value} if rating_value else {},
                )
            )
        return hits

    def detail(self, ref: ProviderRef, ctx: object) -> ProviderRecord | None:
        provider_type = provider_media_type_of(ref.provider_media_type or ref.media_type)
        if provider_type in (ProviderMediaType.SERIES, ProviderMediaType.ANIME):
            info = self._api.tv_detail(ref.external_id)
            if not info:
                info = self._api.movie_detail(ref.external_id)
        else:
            info = self._api.movie_detail(ref.external_id)
            if not info:
                info = self._api.tv_detail(ref.external_id)
        if not info or info.get("localized_message") or not info.get("title"):
            raise ProviderNotFound("douban", f"未找到 {ref.external_id}")
        if provider_type == ProviderMediaType.UNKNOWN:
            provider_type = _infer_provider_type(info)
        record = douban_detail_to_record(
            info,
            media_type=provider_type,
            external_id=ref.external_id,
            content_profile="default",
        )
        return record

    def map_ids(self, ref: ProviderRef, ctx: object) -> list[ProviderRef]:
        record = self.detail(ref, ctx)
        return record.refs if record else []

    def seasons(self, ref: ProviderRef, ctx: object) -> list[SeasonRecord]:
        return []

    def episodes(self, ref: ProviderRef, season: int, ctx: object) -> list[EpisodeRecord]:
        if not (settings.get("media") or {}).get("douban_html_episodes", True):
            return []
        try:
            if self._episode_scraper is not None:
                raw = self._episode_scraper.fetch(ref.external_id, season)
            else:
                raw = episode_queue.get(ref.external_id, season)
        except Exception as exc:  # noqa: BLE001 - HTML 风控失败不影响主流程
            log.warn(f"[Douban]HTML 分集获取失败 {ref.external_id}: {exc}")
            return []
        return [
            EpisodeRecord(
                season_number=int(item.get("season_number") or season),
                episode_number=int(item["episode_number"]),
                title=item.get("title"),
                overview=item.get("overview"),
                air_date=item.get("air_date"),
                still=item.get("still"),
            )
            for item in raw
            if item.get("episode_number") is not None
        ]

    def health(self, ctx: object) -> ProviderHealth:
        return ProviderHealth(provider="douban", ok=True)


def _season_from_scope(scope: str) -> int:
    if scope.startswith("season="):
        try:
            return int(scope.split("=", 1)[1])
        except ValueError:
            return 1
    return 1

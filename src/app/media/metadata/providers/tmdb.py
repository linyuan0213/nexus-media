"""TMDB 原始详情 → ProviderRecord.

纯映射函数，不发起请求；adapter 类在编排层接入。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Protocol

from app.domain.mediatypes import MediaType
from app.infrastructure.cache_system import lru_cache_with_ttl
from app.infrastructure.image_proxy import ImageProxy
from app.media.lookup.tmdb_client import TmdbClient
from app.media.lookup.tmdb_detail import TmdbDetail
from app.media.lookup.tmdb_search import TmdbSearch
from app.media.lookup.tmdb_season import TmdbSeason

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
from .genres import classify_media_type

ImageUrlBuilder = Callable[[str | None], str | None]


class _DetailLike(Protocol):
    def get_detail(
        self,
        tmdbid: str,
        mtype: MediaType,
        language: str | None = None,
        append_to_response: str | None = None,
    ) -> dict[str, Any] | None: ...


class _SeasonLike(Protocol):
    def get_episodes(self, tmdbid: int, season: int) -> list[dict[str, Any]]: ...


class _SearchLike(Protocol):
    def search_movie_infos(self, name: str, year: Any = None) -> list[dict[str, Any]]: ...

    def search_tv_infos(self, name: str, year: Any = None) -> list[dict[str, Any]]: ...


def tmdb_detail_to_record(
    info: dict[str, Any],
    *,
    media_type: MediaType,
    external_id: str | None = None,
    scope: str = "default",
    locale: str | None = None,
    content_profile: str = "default",
    episodes: Sequence[EpisodeRecord] | None = None,
    image_url: ImageUrlBuilder | None = None,
) -> ProviderRecord:
    """把 TMDB movie/tv detail 字典映射为规范记录."""
    media_type, content_profile = classify_media_type(media_type, info.get("genres"), content_profile)
    tmdb_id = str(external_id or info.get("id") or "")
    release_date = info.get("release_date") or info.get("first_air_date")
    runtime = info.get("runtime")
    if runtime is None:
        runtimes = info.get("episode_run_time") or []
        runtime = runtimes[0] if runtimes else None

    refs = [ProviderRef(provider="tmdb", external_id=tmdb_id, media_type=media_type, scope=scope)]
    if info.get("imdb_id"):
        refs.append(ProviderRef(provider="imdb", external_id=str(info["imdb_id"]), media_type=media_type))
    if info.get("external_ids", {}).get("wikidata_id"):
        refs.append(ProviderRef(provider="wikidata", external_id=str(info["external_ids"]["wikidata_id"])))
    if info.get("external_ids", {}).get("tvdb_id"):
        refs.append(
            ProviderRef(
                provider="tvdb",
                external_id=str(info["external_ids"]["tvdb_id"]),
                media_type=media_type,
            )
        )

    images = _images(info, image_url)
    vote_average = info.get("vote_average")

    return ProviderRecord(
        provider="tmdb",
        external_id=tmdb_id,
        refs=refs,
        media_type=media_type,
        content_profile=content_profile,
        locale=locale,
        title=info.get("title") or info.get("name"),
        original_title=info.get("original_title") or info.get("original_name"),
        year=(release_date or "")[:4] or None,
        release_date=release_date,
        runtime=runtime,
        overview=info.get("overview") or None,
        tagline=info.get("tagline") or None,
        original_language=info.get("original_language") or None,
        countries=list(info.get("origin_country") or []),
        spoken_languages=[item.get("name") for item in info.get("spoken_languages") or [] if item.get("name")],
        genres=[item.get("name") for item in info.get("genres") or [] if item.get("name")],
        studios=[item.get("name") for item in info.get("production_companies") or [] if item.get("name")],
        labels=[item.get("name") for item in info.get("networks") or [] if item.get("name")],
        ratings={"tmdb": float(vote_average)} if vote_average is not None else {},
        images=images,
        credits=_credits(info, image_url),
        seasons=_seasons(info, image_url),
        episodes=list(episodes or []),
        extra={
            "tmdb.popularity": info.get("popularity"),
            "tmdb.vote_count": info.get("vote_count"),
            "tmdb.status": info.get("status"),
            "tmdb.homepage": info.get("homepage"),
        },
    )


def _images(info: dict[str, Any], image_url: ImageUrlBuilder | None) -> dict[str, list[ImageAsset]]:
    result: dict[str, list[ImageAsset]] = {}
    if info.get("poster_path"):
        result["poster"] = [ImageAsset(type="poster", url=_image(info["poster_path"], image_url))]
    if info.get("backdrop_path"):
        result["backdrop"] = [ImageAsset(type="backdrop", url=_image(info["backdrop_path"], image_url))]

    raw_images = info.get("images") or {}
    for key, image_type in (("posters", "poster"), ("backdrops", "backdrop"), ("logos", "logo")):
        assets = [
            ImageAsset(type=image_type, url=_image(item.get("file_path"), image_url), locale=item.get("iso_639_1"))
            for item in raw_images.get(key) or []
            if item.get("file_path")
        ]
        if assets:
            result[image_type] = assets
    return result


def _image(path: str | None, image_url: ImageUrlBuilder | None) -> str:
    if not path:
        return ""
    return (image_url(path) or "") if image_url else path


def _credits(info: dict[str, Any], image_url: ImageUrlBuilder | None) -> list[Credit]:
    raw = info.get("credits") or {}
    result: list[Credit] = []
    for member in raw.get("cast") or []:
        if not member.get("name"):
            continue
        result.append(
            Credit(
                name=member["name"],
                role="actor",
                character=member.get("character") or None,
                order=int(member.get("order") or 0),
                provider="tmdb",
                external_id=str(member.get("id")) if member.get("id") else None,
                image_url=_image(member.get("profile_path"), image_url) or None,
            )
        )
    for member in raw.get("crew") or []:
        if not member.get("name"):
            continue
        result.append(
            Credit(
                name=member["name"],
                role=str(member.get("job") or "crew").lower(),
                character=None,
                order=0,
                provider="tmdb",
                external_id=str(member.get("id")) if member.get("id") else None,
                image_url=_image(member.get("profile_path"), image_url) or None,
            )
        )
    return result


def _seasons(info: dict[str, Any], image_url: ImageUrlBuilder | None = None) -> list[SeasonRecord]:
    return [
        SeasonRecord(
            season_number=int(season["season_number"]),
            title=season.get("name"),
            overview=season.get("overview") or None,
            air_date=season.get("air_date"),
            episode_count=season.get("episode_count"),
            poster=_image(season.get("poster_path"), image_url),
        )
        for season in info.get("seasons") or []
        if season.get("season_number") is not None
    ]


HOSTS = {"api.themoviedb.org", "image.tmdb.org"}
RATE = 40


class TmdbProvider:
    """TMDB provider adapter（包装现有 TmdbDetail/TmdbSeason/TmdbSearch）."""

    descriptor = ProviderDescriptor(
        provider_key="tmdb",
        subscription_order=1,
        default_subscription_policy="tmdb_primary",
        display_name="TMDB",
        ref_prefixes=frozenset({"TMDB"}),
        subscription_id_format="{id}",
        default_media_type=MediaType.MOVIE,
        detail_url_template="https://www.themoviedb.org/{media_type}/{external_id}",
        capabilities=frozenset(
            {
                ProviderCapability.SEARCH,
                ProviderCapability.DETAIL,
                ProviderCapability.EXTERNAL_IDS,
                ProviderCapability.SEASONS,
                ProviderCapability.EPISODES,
                ProviderCapability.CREDITS,
                ProviderCapability.IMAGES,
                ProviderCapability.RELEASE_DATES,
            }
        ),
        media_types=frozenset({MediaType.MOVIE, MediaType.TV, MediaType.ANIME}),
        source_tiers=frozenset({SourceTier.API}),
        allowed_hosts=frozenset(HOSTS),
        rate_limit_per_minute=RATE,
    )

    def __init__(
        self,
        detail: _DetailLike | None = None,
        season: _SeasonLike | None = None,
        search: _SearchLike | None = None,
    ) -> None:
        if detail is None or season is None or search is None:
            client = TmdbClient()
            detail = detail or TmdbDetail(client)
            season = season or TmdbSeason(client)
            search = search or TmdbSearch(client)
        self._detail = detail
        self._season = season
        self._search = search

    def search(self, query: SearchQuery, ctx: object) -> list[SearchHit]:
        media_types = [query.media_type] if query.media_type is not None else [MediaType.MOVIE, MediaType.TV]
        hits: list[SearchHit] = []
        seen: set[tuple[str, str]] = set()
        for media_type in media_types:
            if media_type == MediaType.MOVIE:
                raw = self._search.search_movie_infos(query.query, query.year)
            else:
                raw = self._search.search_tv_infos(query.query, query.year)
            for item in raw or []:
                if not item.get("id"):
                    continue
                hit_type, hit_profile = classify_media_type(media_type, item.get("genre_ids"), query.content_profile)
                external_id = str(item.get("id"))
                key = (hit_type.value, external_id)
                if key in seen:
                    continue
                seen.add(key)
                hits.append(
                    SearchHit(
                        provider="tmdb",
                        ref=ProviderRef(
                            provider="tmdb",
                            external_id=external_id,
                            media_type=hit_type,
                        ),
                        title=item.get("title") or item.get("name") or "",
                        year=(item.get("release_date") or item.get("first_air_date") or "")[:4] or None,
                        media_type=hit_type,
                        content_profile=hit_profile,
                        poster=ImageProxy.get_tmdbimage_url(item.get("poster_path"))
                        if item.get("poster_path")
                        else None,
                        score=float(item.get("popularity") or 0.0),
                    )
                )
        return hits

    def detail(self, ref: ProviderRef, ctx: object) -> ProviderRecord | None:
        media_type = ref.media_type or MediaType.MOVIE
        info = self._detail.get_detail(
            ref.external_id,
            media_type,
            append_to_response="credits,images,external_ids",
        )
        if not info:
            raise ProviderNotFound("tmdb", f"未找到 {ref.external_id}")
        episodes: list[EpisodeRecord] = []
        if media_type in {MediaType.TV, MediaType.ANIME}:
            episodes = self._episodes(ref.external_id, _season_from_scope(ref.scope))
        return tmdb_detail_to_record(
            info,
            media_type=media_type,
            external_id=ref.external_id,
            scope=ref.scope,
            episodes=episodes,
            image_url=ImageProxy.get_tmdbimage_url,
        )

    def map_ids(self, ref: ProviderRef, ctx: object) -> list[ProviderRef]:
        record = self.detail(ref, ctx)
        return record.refs if record else []

    def seasons(self, ref: ProviderRef, ctx: object) -> list[SeasonRecord]:
        record = self.detail(ref, ctx)
        return record.seasons if record else []

    def episodes(self, ref: ProviderRef, season: int, ctx: object) -> list[EpisodeRecord]:
        return self._episodes(ref.external_id, season)

    def health(self, ctx: object) -> ProviderHealth:
        return ProviderHealth(provider="tmdb", ok=True)

    @lru_cache_with_ttl(maxsize=256, ttl=21600)
    def _episodes(self, tmdb_id: str, season: int) -> list[EpisodeRecord]:
        raw = self._season.get_episodes(int(tmdb_id), season)
        return [
            EpisodeRecord(
                season_number=int(item.get("season_number") or season),
                episode_number=int(item["episode_number"]),
                title=item.get("name"),
                overview=item.get("overview") or None,
                air_date=item.get("air_date"),
                runtime=item.get("runtime"),
                still=item.get("still_path") or None,
                vote_average=item.get("vote_average"),
            )
            for item in reversed(raw or [])
            if item.get("episode_number") is not None
        ]


def _season_from_scope(scope: str) -> int:
    if scope.startswith("season="):
        try:
            return int(scope.split("=", 1)[1])
        except ValueError:
            return 1
    return 1

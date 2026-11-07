"""Provider 无关的元数据 DTO.

本模块只定义数据结构，不依赖任何具体来源（TMDB/豆瓣/Bangumi）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.domain.media_types import MediaKind, ProviderMediaType, media_type_registry
from app.domain.mediatypes import MediaType


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProviderCapability(StrEnum):
    """Provider 可提供的能力."""

    SEARCH = "search"
    DETAIL = "detail"
    EXTERNAL_IDS = "external_ids"
    SEASONS = "seasons"
    EPISODES = "episodes"
    CREDITS = "credits"
    IMAGES = "images"
    RELEASE_DATES = "release_dates"
    CONTENT_ID = "content_id"
    ACTOR_DETAIL = "actor_detail"
    DISCOVERY = "discovery"


class SourceTier(StrEnum):
    """能力实现层级，合成时 api > html > scraping."""

    API = "api"
    HTML = "html"
    SCRAPING = "scraping"


class ProviderRef(BaseModel):
    """某个外部来源下的稳定引用."""

    provider: str
    external_id: str
    media_type: MediaType | None = None
    provider_media_type: ProviderMediaType | None = None
    media_kind: MediaKind | None = None
    scope: str = "default"
    url: str | None = None
    confidence: float = 1.0

    @model_validator(mode="after")
    def _fill_media_kind(self):
        if self.provider_media_type is None and self.media_type is not None:
            self.provider_media_type = ProviderMediaType.from_value(self.media_type.value)
        if self.media_type is None and self.provider_media_type is not None:
            self.media_type = self.provider_media_type.to_media_type()
        if self.media_kind is None:
            self.media_kind = (
                self.provider_media_type.kind
                if self.provider_media_type is not None
                else media_type_registry.resolve(self.media_type).kind
            )
        return self


class ProviderDescriptor(BaseModel):
    """Provider 自描述信息."""

    provider_key: str
    display_name: str
    detail_url_template: str = ""
    capabilities: frozenset[ProviderCapability] = frozenset()
    provider_media_types: frozenset[ProviderMediaType] = frozenset()
    media_kinds: frozenset[MediaKind] = frozenset()
    content_profiles: frozenset[str] = frozenset()
    ref_prefixes: frozenset[str] = frozenset()
    search_mode: str = ""
    rating_max: int = 10
    default_priority: int = 100
    visibility: Literal["public", "private"] = "public"
    required_permission: str = ""
    result_schema_version: int = 1
    source_tiers: frozenset[SourceTier] = frozenset({SourceTier.API})
    requires_auth: bool = False
    allowed_hosts: frozenset[str] = frozenset()
    rate_limit_per_minute: int = 0
    timeout_seconds: int = 30
    circuit_failures: int = 3
    circuit_cooldown_seconds: int = 60
    subscription_id_format: str = ""
    subscription_ref: bool = False
    default_provider_media_type: ProviderMediaType | None = None
    default_content_profile: str = "default"
    subscription_order: int = 100
    default_subscription_policy: str = ""
    virtual: bool = False
    uniqueid_fallback: str = ""


class ImageAsset(BaseModel):
    type: str
    url: str
    width: int | None = None
    height: int | None = None
    locale: str | None = None
    provider: str | None = None


class Credit(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)
    role: str = "actor"
    character: str | None = None
    order: int = 0
    provider: str | None = None
    external_id: str | None = None
    person_id: str | None = None
    image_url: str | None = None


class SeasonRecord(BaseModel):
    season_number: int
    title: str | None = None
    overview: str | None = None
    air_date: str | None = None
    episode_count: int | None = None
    poster: str | None = None


class EpisodeRecord(BaseModel):
    season_number: int
    episode_number: int
    title: str | None = None
    overview: str | None = None
    air_date: str | None = None
    runtime: int | None = None
    still: str | None = None
    vote_average: float | None = None


class ProviderRecord(BaseModel):
    """单个 provider 返回的规范化记录."""

    schema_version: int = 1
    source_tier: SourceTier | None = None
    provider: str
    external_id: str
    refs: list[ProviderRef] = Field(default_factory=list)
    media_type: MediaType = MediaType.UNKNOWN
    provider_media_type: ProviderMediaType | None = None
    media_kind: MediaKind | None = None
    content_profile: str = "default"
    locale: str | None = None

    title: str | None = None
    original_title: str | None = None
    aliases: list[str] = Field(default_factory=list)
    year: str | None = None
    release_date: str | None = None
    runtime: int | None = None
    overview: str | None = None
    tagline: str | None = None
    original_language: str | None = None

    countries: list[str] = Field(default_factory=list)
    spoken_languages: list[str] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    studios: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    series: list[str] = Field(default_factory=list)

    ratings: dict[str, float] = Field(default_factory=dict)
    images: dict[str, list[ImageAsset]] = Field(default_factory=dict)
    credits: list[Credit] = Field(default_factory=list)
    seasons: list[SeasonRecord] = Field(default_factory=list)
    episodes: list[EpisodeRecord] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)
    fetched_at: datetime = Field(default_factory=_utcnow)

    @model_validator(mode="after")
    def _fill_media_kind(self):
        if self.provider_media_type is None:
            self.provider_media_type = ProviderMediaType.from_value(self.media_type.value)
        if self.media_type == MediaType.UNKNOWN and self.provider_media_type != ProviderMediaType.UNKNOWN:
            self.media_type = self.provider_media_type.to_media_type()
        if self.media_kind is None:
            self.media_kind = self.provider_media_type.kind
        return self


class FieldValue(BaseModel):
    """合成后的字段值及其来源."""

    value: Any
    provider: str
    external_id: str
    confidence: float = 1.0
    locale: str | None = None
    fetched_at: datetime = Field(default_factory=_utcnow)
    locked: bool = False


class MediaMetadata(BaseModel):
    """跨 provider 合成后的规范元数据快照."""

    schema_version: int = 1
    identity_id: str
    media_type: MediaType = MediaType.UNKNOWN
    media_kind: MediaKind | None = None
    content_profile: str = "default"
    scope: str = "default"
    primary_provider: str | None = None
    refs: list[ProviderRef] = Field(default_factory=list)
    fields: dict[str, FieldValue] = Field(default_factory=dict)

    ratings: dict[str, float] = Field(default_factory=dict)
    aliases: list[str] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    spoken_languages: list[str] = Field(default_factory=list)
    studios: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    series: list[str] = Field(default_factory=list)

    credits: list[Credit] = Field(default_factory=list)
    seasons: list[SeasonRecord] = Field(default_factory=list)
    episodes: list[EpisodeRecord] = Field(default_factory=list)
    images: dict[str, list[ImageAsset]] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)

    snapshot_hash: str = ""
    fetched_at: datetime = Field(default_factory=_utcnow)


class SearchQuery(BaseModel):
    query: str
    media_type: MediaType | None = None
    content_profile: str = "default"
    year: str | None = None
    locale: str | None = None
    limit: int = 20


class SearchHit(BaseModel):
    provider: str
    ref: ProviderRef
    title: str
    year: str | None = None
    media_type: MediaType = MediaType.UNKNOWN
    media_kind: MediaKind | None = None
    content_profile: str = "default"
    poster: str | None = None
    score: float = 0.0
    extra: dict[str, Any] = Field(default_factory=dict)


class ProviderHealth(BaseModel):
    provider: str
    ok: bool
    degraded: bool = False
    message: str = ""
    latency_ms: int | None = None
    checked_at: datetime = Field(default_factory=_utcnow)


class FacetValue(BaseModel):
    value: str
    label: str | None = None
    count: int | None = None


class DiscoveryFeed(BaseModel):
    schema_version: int = 1
    key: str
    title: str
    kind: Literal["ranking", "trending", "latest", "calendar", "seasonal", "collection", "search"] = "latest"
    icon: str | None = None
    facets: list[str] = Field(default_factory=list)
    page_size: int = 20


class DiscoveryItem(BaseModel):
    schema_version: int = 1
    provider: str
    ref: ProviderRef
    content_profile: str = "default"
    title: str
    original_title: str | None = None
    year: str | None = None
    poster: str | None = None
    backdrop: str | None = None
    rating: dict[str, float] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    anchor_ref: ProviderRef | None = None
    actions: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class DiscoveryPage(BaseModel):
    schema_version: int = 1
    items: list[DiscoveryItem] = Field(default_factory=list)
    page: int = 1
    has_more: bool = False
    facets: dict[str, list[FacetValue]] = Field(default_factory=dict)
    error: str | None = None
    retryable: bool = False


class Detection(BaseModel):
    """MatchProfile 的检测结果."""

    content_profile: str
    confidence: float
    anchor_hint: ProviderRef | None = None
    base_media_type: MediaType | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class MatchResult(BaseModel):
    """MatchProfile 的匹配结果."""

    content_profile: str
    candidates: list[SearchHit] = Field(default_factory=list)
    anchor_ref: ProviderRef | None = None
    confidence: float = 0.0

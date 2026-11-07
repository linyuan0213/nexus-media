"""Provider 协议定义.

业务层只依赖协议，不 import 具体 adapter。
"""

from __future__ import annotations

from typing import Protocol

from app.domain.media_types import ProviderMediaType

from .models import (
    Detection,
    DiscoveryFeed,
    DiscoveryPage,
    EpisodeRecord,
    MatchResult,
    ProviderDescriptor,
    ProviderHealth,
    ProviderRecord,
    ProviderRef,
    SearchHit,
    SearchQuery,
    SeasonRecord,
)


class MetadataProvider(Protocol):
    descriptor: ProviderDescriptor

    def search(self, query: SearchQuery, ctx: object) -> list[SearchHit]: ...

    def detail(self, ref: ProviderRef, ctx: object) -> ProviderRecord | None: ...

    def map_ids(self, ref: ProviderRef, ctx: object) -> list[ProviderRef]: ...

    def seasons(self, ref: ProviderRef, ctx: object) -> list[SeasonRecord]: ...

    def episodes(self, ref: ProviderRef, season: int, ctx: object) -> list[EpisodeRecord]: ...

    def health(self, ctx: object) -> ProviderHealth: ...


class DiscoveryProvider(Protocol):
    descriptor: ProviderDescriptor

    def feeds(self, ctx: object) -> list[DiscoveryFeed]: ...

    def items(self, feed: str, page: int, filters: dict, ctx: object) -> DiscoveryPage: ...


class MatchProfile(Protocol):
    key: str
    base_media_type: ProviderMediaType
    priority: int

    def detect(self, ctx: object) -> Detection | None: ...

    def match(self, parsed: object, ctx: object) -> MatchResult: ...

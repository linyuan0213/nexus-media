"""内置 movie/tv/anime MatchProfile，复用旧 infer_type 保证结果一致."""

from __future__ import annotations

from app.domain.media_types import ProviderMediaType

from ...metadata.models import Detection, MatchResult
from ...metadata.registry import MetadataRegistry
from ...metadata.registry import registry as global_registry
from .type_inferrer import infer_type
from .types import ParseContext


class _BuiltinMatchProfile:
    base_media_type = ProviderMediaType.SERIES
    content_profile = "default"
    priority = 10

    def detect(self, ctx: ParseContext) -> Detection | None:
        if infer_type(ctx) != self.base_media_type:
            return None
        return Detection(
            content_profile=self.content_profile,
            confidence=0.9,
            base_media_type=self.base_media_type,
        )

    def match(self, parsed: object, ctx: object) -> MatchResult:
        return MatchResult(content_profile=self.content_profile)


class MovieMatchProfile(_BuiltinMatchProfile):
    key = "movie"
    base_media_type = ProviderMediaType.MOVIE
    priority = 10


class TvMatchProfile(_BuiltinMatchProfile):
    key = "tv"
    base_media_type = ProviderMediaType.SERIES
    priority = 20


class AnimeMatchProfile(_BuiltinMatchProfile):
    key = "anime"
    base_media_type = ProviderMediaType.ANIME
    content_profile = "anime"
    priority = 30


def ensure_builtin_match_profiles(registry: MetadataRegistry | None = None) -> None:
    target = registry or global_registry
    for key, profile in (
        ("movie", MovieMatchProfile()),
        ("tv", TvMatchProfile()),
        ("anime", AnimeMatchProfile()),
    ):
        if target.get_profile("match", key) is None:
            target.register_profile("match", key, profile)

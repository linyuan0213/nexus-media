"""搜索主体的统一类型/身份决策，供 Web 搜索、订阅搜索和下载匹配共用."""

from dataclasses import dataclass
from typing import Literal

from app.domain.media_types import MediaKind, media_type_registry
from app.domain.mediatypes import MediaType

_TITLE_PROFILES = {"default", "anime", "tv", "movie"}


@dataclass(frozen=True)
class SearchSubject:
    raw_type: MediaType | None
    display_type: MediaType | None
    provider_type: MediaType | None
    content_profile: str
    code_identity: bool
    search_mode: Literal["code", "title"]

    @classmethod
    def classify(
        cls,
        media_type: object = None,
        content_profile: object = "",
        anchor_provider: object = "",
        external_id: object = "",
    ) -> "SearchSubject":
        raw = MediaType.from_string(str(media_type or ""))
        raw_type = raw if raw != MediaType.UNKNOWN else None
        profile = str(content_profile or "").strip() or "default"
        provider = str(anchor_provider or "").strip()
        external = str(external_id or "").strip()

        descriptor = media_type_registry.resolve_profile(profile) or media_type_registry.resolve(media_type, profile)
        code_identity = (
            descriptor.code_identity
            or profile not in _TITLE_PROFILES
            or provider == "content_id"
            or external.startswith("content_id:")
        )
        if provider == "bangumi" and raw_type != MediaType.MOVIE:
            display = MediaType.ANIME
        elif profile == "anime" or raw_type == MediaType.ANIME or descriptor.key == "anime":
            display = MediaType.ANIME
        elif raw_type in (MediaType.MOVIE, MediaType.TV):
            display = raw_type
        elif descriptor.kind == MediaKind.MOVIE:
            display = MediaType.MOVIE
        elif descriptor.kind == MediaKind.EPISODIC:
            display = MediaType.TV
        else:
            display = None
        if display == MediaType.ANIME:
            provider_type = MediaType.TV
        else:
            provider_type = display
        return cls(
            raw_type=raw_type,
            display_type=display,
            provider_type=provider_type,
            content_profile=profile,
            code_identity=code_identity,
            search_mode="code" if code_identity else "title",
        )

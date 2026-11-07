"""搜索主体的统一类型/身份决策，供 Web 搜索、订阅搜索和下载匹配共用."""

from dataclasses import dataclass
from typing import Literal

from app.domain.media_types import MediaKind, ProviderMediaType, media_type_registry

_TITLE_PROFILES = {"default", "anime", "tv", "movie"}


@dataclass(frozen=True)
class SearchSubject:
    raw_type: ProviderMediaType | None
    display_type: ProviderMediaType | None
    provider_type: ProviderMediaType | None
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
        raw = ProviderMediaType.from_value(str(media_type or ""))
        raw_type = raw if raw != ProviderMediaType.UNKNOWN else None
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
        if provider == "bangumi" and raw_type != ProviderMediaType.MOVIE:
            display = ProviderMediaType.ANIME
        elif profile == "anime" or raw_type == ProviderMediaType.ANIME or descriptor.key == "anime":
            display = ProviderMediaType.ANIME
        elif raw_type in (ProviderMediaType.MOVIE, ProviderMediaType.SERIES):
            display = raw_type
        elif descriptor.kind == MediaKind.MOVIE:
            display = ProviderMediaType.MOVIE
        elif descriptor.kind == MediaKind.EPISODIC:
            display = ProviderMediaType.SERIES
        else:
            display = None
        if display == ProviderMediaType.ANIME:
            provider_type = ProviderMediaType.SERIES
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

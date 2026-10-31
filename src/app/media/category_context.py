"""跨数据源分类上下文."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .category_taxonomy import load_taxonomy


@dataclass
class CategoryContext:
    genres: set[str] = field(default_factory=set)
    languages: set[str] = field(default_factory=set)
    countries: set[str] = field(default_factory=set)
    tags: set[str] = field(default_factory=set)
    content_profiles: set[str] = field(default_factory=set)
    providers: set[str] = field(default_factory=set)
    prefix: str | None = None
    flags: set[str] = field(default_factory=set)
    raw: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, set[str]] = field(default_factory=dict)

    @classmethod
    def from_info(
        cls,
        info: dict[str, Any] | None,
        *,
        media_type: str | None = None,
        provider: str | None = None,
        content_profile: str | None = None,
        source: str | None = None,
    ) -> CategoryContext:
        if not info:
            return cls()
        taxonomy = load_taxonomy()
        genres = taxonomy.genre_keys(info.get("genres"), media_type)
        genres.update(taxonomy.genre_keys(info.get("genre_ids"), media_type))
        languages = taxonomy.language_codes(info.get("original_language"))
        languages.update(taxonomy.language_codes(info.get("spoken_languages")))
        languages.update(taxonomy.language_codes(info.get("languages")))
        countries = taxonomy.country_codes(info.get("origin_country"))
        countries.update(taxonomy.country_codes(info.get("production_countries")))
        countries.update(taxonomy.country_codes(info.get("countries")))
        tags = _text_set(info.get("tags"))
        providers = _text_set(info.get("providers"))
        if provider:
            providers.add(provider.lower())
        profiles = _text_set(info.get("content_profiles"))
        profile = content_profile or info.get("content_profile")
        if profile:
            profiles.add(str(profile).strip().lower())
        source_name = str(source or provider or "unknown").strip().lower()
        provenance: dict[str, set[str]] = {}
        for field_name, values in (
            ("genres", genres),
            ("languages", languages),
            ("countries", countries),
            ("tags", tags),
            ("content_profiles", profiles),
            ("providers", providers),
            ("flags", _text_set(info.get("flags"))),
        ):
            if values:
                provenance[field_name] = {source_name}
        return cls(
            genres=genres,
            languages=languages,
            countries=countries,
            tags=tags,
            content_profiles=profiles,
            providers=providers,
            prefix=_text_or_none(info.get("prefix") or info.get("content_id")),
            flags=_text_set(info.get("flags")),
            raw=dict(info),
            provenance=provenance,
        )

    def merge(self, other: CategoryContext) -> CategoryContext:
        return CategoryContext(
            genres=self.genres | other.genres,
            languages=self.languages | other.languages,
            countries=self.countries | other.countries,
            tags=self.tags | other.tags,
            content_profiles=self.content_profiles | other.content_profiles,
            providers=self.providers | other.providers,
            prefix=self.prefix or other.prefix,
            flags=self.flags | other.flags,
            raw={**self.raw, **other.raw},
            provenance={
                key: self.provenance.get(key, set()) | other.provenance.get(key, set())
                for key in set(self.provenance) | set(other.provenance)
            },
        )


def _text_set(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, dict):
        value = list(value.values())
    if not isinstance(value, (list, tuple, set)):
        value = [value]
    result: set[str] = set()
    for item in value:
        if isinstance(item, dict):
            item = item.get("name") or item.get("value") or ""
        text = str(item).strip().lower()
        if text:
            result.add(text)
    return result


def _text_or_none(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None

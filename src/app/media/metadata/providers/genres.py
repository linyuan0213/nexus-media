"""通用题材分类：把各元数据来源统一映射到电影/电视剧/动漫."""

from __future__ import annotations

from typing import Any, Iterable

from app.core.constants import ANIME_GENREIDS
from app.domain.media_types import MediaKind, ProviderMediaType, provider_media_type_of

_ANIME_GENRE_NAMES = {"动画", "動畫", "アニメ", "animation"}
_ANIME_GENRE_IDS = set(ANIME_GENREIDS)


def is_anime_genre(genres: Iterable[Any] | None) -> bool:
    """兼容 TMDB [{id,name}]、豆瓣 [str] 与插件自定义题材列表."""
    for genre in genres or []:
        if isinstance(genre, dict):
            genre_id = str(genre.get("id") or "").strip()
            name = str(genre.get("name") or "").strip()
        else:
            genre_id = str(genre).strip() if str(genre).strip().isdigit() else ""
            name = str(genre).strip()
        if genre_id and genre_id in _ANIME_GENRE_IDS:
            return True
        if name and name.lower() in _ANIME_GENRE_NAMES:
            return True
    return False


def classify_provider_media_type(
    media_type: ProviderMediaType,
    genres: Iterable[Any] | None,
    content_profile: str = "default",
) -> tuple[ProviderMediaType, str]:
    """按题材细化 provider 类型；动漫属于连续性内容，但保留独立画像."""
    if content_profile == "anime":
        return ProviderMediaType.ANIME, "anime"
    if media_type.kind in (MediaKind.EPISODIC, MediaKind.UNKNOWN) and is_anime_genre(genres):
        return ProviderMediaType.ANIME, "anime"
    return media_type, content_profile


def classify_media_type(
    media_type: ProviderMediaType,
    genres: Iterable[Any] | None,
    content_profile: str = "default",
) -> tuple[ProviderMediaType, str]:
    """兼容旧调用的内部类型分类入口."""
    provider_type, profile = classify_provider_media_type(
        provider_media_type_of(media_type),
        genres,
        content_profile,
    )
    return provider_type, profile

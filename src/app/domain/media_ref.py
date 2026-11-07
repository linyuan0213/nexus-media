"""来源无关的媒体引用与合成主体."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domain.media_types import MediaKind, ProviderMediaType, media_type_registry


@dataclass(frozen=True)
class MediaRef:
    """上层统一使用的媒体锚点；不携带任何 provider 专属结构."""

    provider: str
    external_id: str
    scope: str = "default"
    media_type: ProviderMediaType | None = None
    provider_media_type: ProviderMediaType | None = None
    media_kind: MediaKind | None = None

    def __post_init__(self) -> None:
        if self.provider_media_type is None and self.media_type is not None:
            object.__setattr__(
                self,
                "provider_media_type",
                ProviderMediaType.from_value(self.media_type.value),
            )
        if self.media_kind is None:
            object.__setattr__(
                self,
                "media_kind",
                self.provider_media_type.kind
                if self.provider_media_type is not None
                else media_type_registry.resolve(self.media_type).kind,
            )


def normalize_identity_key(value: Any) -> str:
    """归一化订阅/缺失季集使用的媒体键.

    兼容历史数字 TMDB ID、``TMDB:``/``DB:``/``BG:`` 前缀，以及新的
    ``provider:external_id`` 和 ``id:<identity_id>`` 形式。
    """
    text = str(value or "").strip()
    if not text:
        return ""
    upper = text.upper()
    if upper.startswith("DB:"):
        return f"douban:{text[3:]}"
    if upper.startswith("BG:"):
        return f"bangumi:{text[3:]}"
    if upper.startswith("TMDB:"):
        return f"tmdb:{text[5:]}"
    if text.startswith("id:"):
        return text
    if ":" in text:
        provider, external = text.split(":", 1)
        return f"{provider.strip().lower()}:{external.strip()}"
    if text.isdigit():
        return f"tmdb:{text}"
    return text


def canonical_metadata_ref(media: Any) -> str:
    """返回新的统一引用；不再把数字/DB:/BG: 当作运行时主键。"""
    if media is None:
        return ""
    explicit = str(getattr(media, "metadata_ref", "") or "").strip()
    if explicit:
        return explicit
    identity_id = str(getattr(media, "identity_id", "") or "").strip()
    if identity_id:
        return f"id:{identity_id}"
    provider = str(getattr(media, "anchor_provider", "") or "").strip().lower()
    external = str(getattr(media, "anchor_external_id", "") or "").strip()
    if provider and external:
        return f"{provider}:{external}"
    if provider == "tmdb" or not provider:
        tmdb_id = str(getattr(media, "tmdb_id", "") or "").strip()
        if tmdb_id.isdigit():
            return f"tmdb:{tmdb_id}"
    return ""


def is_tmdb_media(media: Any) -> bool:
    provider = str(getattr(media, "anchor_provider", "") or "").strip().lower()
    if provider:
        return provider == "tmdb"
    return str(getattr(media, "tmdb_id", "") or "").strip().isdigit()


def media_identity_key(media: Any) -> str:
    """返回媒体对象的稳定匹配键；优先 identity_id，其次 anchor。"""
    if media is None:
        return ""
    identity_id = getattr(media, "identity_id", None)
    if isinstance(identity_id, str) and identity_id.strip():
        return f"id:{identity_id.strip()}"
    get_ref = getattr(media, "get_media_ref", None)
    ref = get_ref() if callable(get_ref) else None
    if isinstance(ref, MediaRef) and ref.provider and ref.external_id:
        return normalize_identity_key(f"{ref.provider}:{ref.external_id}")
    provider = getattr(media, "anchor_provider", None)
    external = getattr(media, "anchor_external_id", None)
    if isinstance(provider, str) and provider.strip() and isinstance(external, str) and external.strip():
        return normalize_identity_key(f"{provider}:{external}")
    tmdb_id = getattr(media, "tmdb_id", None)
    if isinstance(tmdb_id, (str, int)):
        return normalize_identity_key(tmdb_id)
    return ""


def identity_keys_match(left: Any, right: Any) -> bool:
    return bool(normalize_identity_key(left)) and normalize_identity_key(left) == normalize_identity_key(right)


@dataclass
class MediaSubject:
    """供 Composer 使用的最小媒体主体，替代 SimpleNamespace/MediaInfo 鸭子类型."""

    media_type: ProviderMediaType
    tmdb_id: str = ""
    douban_id: str | None = None
    anchor_provider: str = ""
    anchor_external_id: str = ""
    content_profile: str = "default"
    title: str | None = None
    year: str | None = None
    keyword: str | None = None
    begin_season: int | None = None
    extra: dict[str, Any] | None = None

    @property
    def type(self) -> ProviderMediaType:
        return self.media_type

    def get_season_seq(self) -> int:
        return int(self.begin_season or 0)

    def get_media_ref(self) -> MediaRef | None:
        if self.anchor_provider and self.anchor_external_id:
            return MediaRef(
                provider=self.anchor_provider,
                external_id=self.anchor_external_id,
                media_type=self.media_type,
            )
        if str(self.tmdb_id or "").isdigit():
            return MediaRef(provider="tmdb", external_id=str(self.tmdb_id), media_type=self.media_type)
        if self.douban_id:
            return MediaRef(provider="douban", external_id=str(self.douban_id), media_type=self.media_type)
        return None


def media_series_scope_key(media: Any) -> str:
    """订阅/下载去重键：优先内部 series_key + 季，其次回退现有身份键."""
    raw_series_key = getattr(media, "series_key", "")
    series_key = raw_series_key.strip() if isinstance(raw_series_key, str) else ""
    if not series_key:
        return media_identity_key(media)
    season = getattr(media, "begin_season", None)
    if season is None and hasattr(media, "get_season_seq"):
        try:
            season = media.get_season_seq()
        except (TypeError, ValueError):
            season = None
    if season is None:
        return series_key
    try:
        return f"{series_key}:S{int(season):02d}"
    except (TypeError, ValueError):
        return series_key

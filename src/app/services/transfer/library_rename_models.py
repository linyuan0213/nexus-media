"""批量重命名内部数据模型."""

from dataclasses import dataclass, field
from typing import Any

from app.domain.media_types import ProviderMediaType
from app.media.models import MediaInfo
from app.storage.backends.base import StorageBackend


@dataclass(frozen=True)
class LibraryRoot:
    """一个媒体库根目录及其存储后端."""

    media_type: ProviderMediaType
    root: str
    backend_id: str
    backend: StorageBackend


@dataclass
class RenameScope:
    """批量重命名范围与开关."""

    media_types: list[ProviderMediaType] = field(
        default_factory=lambda: [ProviderMediaType.MOVIE, ProviderMediaType.SERIES, ProviderMediaType.ANIME]
    )
    roots: list[str] = field(default_factory=list)
    layout_mode: str = "full"
    preserve_current_category: bool = True
    reorganize_category: bool = False
    use_mediaserver_metadata: bool = True
    allow_online_metadata: bool = False
    reidentify_no_metadata: bool = False
    limit: int = 5000
    server_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "media_types": [m.value for m in self.media_types],
            "roots": list(self.roots),
            "layout_mode": self.layout_mode,
            "preserve_current_category": self.preserve_current_category,
            "reorganize_category": self.reorganize_category,
            "use_mediaserver_metadata": self.use_mediaserver_metadata,
            "allow_online_metadata": self.allow_online_metadata,
            "reidentify_no_metadata": self.reidentify_no_metadata,
            "limit": self.limit,
            "server_id": self.server_id,
        }


@dataclass
class ResolvedMetadata:
    """解析后的媒体信息及来源."""

    media: MediaInfo
    source: str
    confidence: str
    origin: str = ""
    source_filename: str | None = None
    episode_title: str | None = None
    en_title: str | None = None
    online_fields: list[str] = field(default_factory=list)
    reason: str | None = None
    history_ids: list[int] = field(default_factory=list)
    is_manual: bool = False

    def snapshot(self) -> dict[str, Any]:
        media = self.media
        return {
            "type": media.type.value if media.type else "",
            "title": media.title or "",
            "year": media.year or "",
            "tmdbid": media.tmdb_id or "",
            "anchor_provider": media.anchor_provider,
            "anchor_external_id": media.anchor_external_id,
            "identity_id": media.identity_id,
            "content_profile": media.content_profile,
            "links": media.get_detail_links(),
            "imdbid": media.imdb_id or "",
            "original_title": media.original_title or "",
            "season": media.begin_season,
            "end_season": media.end_season,
            "episode": media.begin_episode,
            "end_episode": media.end_episode,
            "total_episodes": media.total_episodes,
            "season_episode_count": _season_episode_count(media),
            "category": media.category,
            "source_filename": self.source_filename,
            "source": self.source,
            "origin": self.origin,
            "confidence": self.confidence,
            "episode_title": self.episode_title,
            "en_title": self.en_title,
            "online_fields": list(self.online_fields),
            "history_ids": list(self.history_ids),
            "is_manual": self.is_manual,
            "org_string": media.org_string,
            "rev_string": media.rev_string,
            "resource_type": media.resource_type,
            "resource_effect": media.resource_effect,
            "resource_pix": media.resource_pix,
            "resource_team": media.resource_team,
            "customization": media.customization,
            "video_encode": media.video_encode,
            "audio_encode": media.audio_encode,
            "part": media.part,
            "provider_data": _minimal_tmdb_info(media),
        }


def _season_episode_count(media: MediaInfo) -> int | None:
    seasons = media.provider_data.get("seasons") if isinstance(media.provider_data, dict) else None
    if not seasons or media.begin_season is None:
        return None
    for season in seasons:
        if isinstance(season, dict) and season.get("season_number") == media.begin_season:
            count = season.get("episode_count")
            return int(count) if count else None
    return None


def _minimal_tmdb_info(media: MediaInfo) -> dict[str, Any]:
    info = media.provider_data if isinstance(media.provider_data, dict) else {}
    return {
        "id": info.get("id") or media.tmdb_id,
        "seasons": info.get("seasons") or [],
    }

"""
RSS 种子领域实体
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SubscribeTorrentEntity:
    """RSS 种子实体"""

    id: int
    torrent_name: str | None
    enclosure: str | None
    type: str | None
    title: str | None
    year: str | None
    season: str | None
    episode: str | None

    @classmethod
    def from_orm(cls, orm_model) -> SubscribeTorrentEntity | None:
        if orm_model is None:
            return None
        return cls(
            id=getattr(orm_model, "ID", 0),
            torrent_name=getattr(orm_model, "TORRENT_NAME", None),
            enclosure=getattr(orm_model, "ENCLOSURE", None),
            type=getattr(orm_model, "TYPE", None),
            title=getattr(orm_model, "TITLE", None),
            year=getattr(orm_model, "YEAR", None),
            season=getattr(orm_model, "SEASON", None),
            episode=getattr(orm_model, "EPISODE", None),
        )

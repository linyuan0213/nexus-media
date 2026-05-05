# -*- coding: utf-8 -*-
"""
RSS 种子领域实体
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class RssTorrentEntity:
    """RSS 种子实体"""
    id: int
    torrent_name: Optional[str]
    enclosure: Optional[str]
    type: Optional[str]
    title: Optional[str]
    year: Optional[str]
    season: Optional[str]
    episode: Optional[str]

    @classmethod
    def from_orm(cls, orm_model) -> Optional["RssTorrentEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=getattr(orm_model, 'ID', 0),
            torrent_name=getattr(orm_model, 'TORRENT_NAME', None),
            enclosure=getattr(orm_model, 'ENCLOSURE', None),
            type=getattr(orm_model, 'TYPE', None),
            title=getattr(orm_model, 'TITLE', None),
            year=getattr(orm_model, 'YEAR', None),
            season=getattr(orm_model, 'SEASON', None),
            episode=getattr(orm_model, 'EPISODE', None),
        )

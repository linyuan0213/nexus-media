# -*- coding: utf-8 -*-
"""
转移领域实体
定义TransferHistory/TransferUnknown/TransferBlacklist的领域模型
"""
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class TransferHistoryEntity:
    """转移历史实体"""
    id: int
    mode: str
    media_type: str
    category: str
    tmdb_id: int
    title: str
    year: str
    season_episode: str
    source: str
    source_path: str
    source_filename: str
    dest: str
    dest_path: str
    dest_filename: str
    date: str

    @classmethod
    def from_orm(cls, orm_model) -> Optional["TransferHistoryEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            mode=orm_model.MODE or "",
            media_type=orm_model.TYPE or "",
            category=orm_model.CATEGORY or "",
            tmdb_id=orm_model.TMDBID or 0,
            title=orm_model.TITLE or "",
            year=orm_model.YEAR or "",
            season_episode=orm_model.SEASON_EPISODE or "",
            source=orm_model.SOURCE or "",
            source_path=orm_model.SOURCE_PATH or "",
            source_filename=orm_model.SOURCE_FILENAME or "",
            dest=orm_model.DEST or "",
            dest_path=orm_model.DEST_PATH or "",
            dest_filename=orm_model.DEST_FILENAME or "",
            date=orm_model.DATE or ""
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "mode": self.mode,
            "type": self.media_type,
            "category": self.category,
            "tmdbid": self.tmdb_id,
            "title": self.title,
            "year": self.year,
            "season_episode": self.season_episode,
            "source": self.source,
            "source_path": self.source_path,
            "source_filename": self.source_filename,
            "dest": self.dest,
            "dest_path": self.dest_path,
            "dest_filename": self.dest_filename,
            "date": self.date,
        }


@dataclass
class TransferUnknownEntity:
    """未知转移记录实体"""
    id: int
    path: str
    dest: str
    mode: str
    state: str

    @classmethod
    def from_orm(cls, orm_model) -> Optional["TransferUnknownEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            path=orm_model.PATH or "",
            dest=orm_model.DEST or "",
            mode=orm_model.MODE or "",
            state=orm_model.STATE or ""
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "path": self.path,
            "dest": self.dest,
            "mode": self.mode,
            "state": self.state,
        }


@dataclass
class TransferBlacklistEntity:
    """转移黑名单实体"""
    id: int
    path: str

    @classmethod
    def from_orm(cls, orm_model) -> Optional["TransferBlacklistEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            path=orm_model.PATH or ""
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "path": self.path,
        }

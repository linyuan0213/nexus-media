# -*- coding: utf-8 -*-
"""
插件历史 / TMDB黑名单领域实体
对应 PLUGIN_HISTORY / TMDB_BLACKLIST 表
"""
from dataclasses import dataclass, fields
from typing import Any, Dict, List, Optional


@dataclass
class PluginHistoryEntity:
    """插件历史实体"""
    id: int
    plugin_id: str
    key: str
    value: str
    date: str

    @classmethod
    def from_orm(cls, orm_model) -> Optional["PluginHistoryEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            plugin_id=orm_model.PLUGIN_ID or "",
            key=orm_model.KEY or "",
            value=orm_model.VALUE or "",
            date=orm_model.DATE or "",
        )

    def __getattr__(self, name: str):
        lower_name = name.lower()
        if lower_name in {f.name for f in fields(self)}:
            return getattr(self, lower_name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "plugin_id": self.plugin_id,
            "key": self.key,
            "value": self.value,
            "date": self.date,
        }


@dataclass
class TmdbBlacklistEntity:
    """TMDB黑名单实体"""
    id: int
    tmdb_id: str
    title: Optional[str]
    year: Optional[str]
    media_type: Optional[str]
    poster_path: Optional[str]
    backdrop_path: Optional[str]
    note: Optional[str]

    @classmethod
    def from_orm(cls, orm_model) -> Optional["TmdbBlacklistEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            tmdb_id=orm_model.TMDB_ID or "",
            title=getattr(orm_model, 'TITLE', None),
            year=getattr(orm_model, 'YEAR', None),
            media_type=getattr(orm_model, 'MEDIA_TYPE', None),
            poster_path=getattr(orm_model, 'POSTER_PATH', None),
            backdrop_path=getattr(orm_model, 'BACKDROP_PATH', None),
            note=getattr(orm_model, 'NOTE', None),
        )

    def __getattr__(self, name: str):
        lower_name = name.lower()
        if lower_name in {f.name for f in fields(self)}:
            return getattr(self, lower_name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tmdb_id": self.tmdb_id,
            "title": self.title,
            "year": self.year,
            "media_type": self.media_type,
            "poster_path": self.poster_path,
            "backdrop_path": self.backdrop_path,
            "note": self.note,
        }

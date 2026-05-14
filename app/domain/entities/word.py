"""
自定义识别词领域实体
对应 CUSTOM_WORDS / CUSTOM_WORD_GROUPS 表
"""

from dataclasses import dataclass, fields
from typing import Any, Optional


@dataclass
class CustomWordEntity:
    """自定义识别词实体"""

    id: int
    replaced: str | None
    replace: str | None
    front: str | None
    back: str | None
    offset: str | None
    type: int
    group_id: int
    season: int
    enabled: int
    regex: int
    help: str | None
    note: str | None

    @classmethod
    def from_orm(cls, orm_model) -> Optional["CustomWordEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            replaced=getattr(orm_model, "REPLACED", None),
            replace=getattr(orm_model, "REPLACE", None),
            front=getattr(orm_model, "FRONT", None),
            back=getattr(orm_model, "BACK", None),
            offset=getattr(orm_model, "OFFSET", None),
            type=getattr(orm_model, "TYPE", 1),
            group_id=getattr(orm_model, "GROUP_ID", 0),
            season=getattr(orm_model, "SEASON", 0),
            enabled=getattr(orm_model, "ENABLED", 1),
            regex=getattr(orm_model, "REGEX", 0),
            help=getattr(orm_model, "HELP", None),
            note=getattr(orm_model, "NOTE", None),
        )

    def __getattr__(self, name: str):
        lower_name = name.lower()
        if lower_name in {f.name for f in fields(self)}:
            return getattr(self, lower_name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "replaced": self.replaced,
            "replace": self.replace,
            "front": self.front,
            "back": self.back,
            "offset": self.offset,
            "type": self.type,
            "group_id": self.group_id,
            "season": self.season,
            "enabled": self.enabled,
            "regex": self.regex,
            "help": self.help,
            "note": self.note,
        }


@dataclass
class CustomWordGroupEntity:
    """自定义识别词组实体"""

    id: int
    title: str | None
    year: str | None
    type: int
    tmdbid: int
    season_count: int
    note: str | None

    @classmethod
    def from_orm(cls, orm_model) -> Optional["CustomWordGroupEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            title=getattr(orm_model, "TITLE", None),
            year=getattr(orm_model, "YEAR", None),
            type=getattr(orm_model, "TYPE", 0),
            tmdbid=getattr(orm_model, "TMDBID", 0),
            season_count=getattr(orm_model, "SEASON_COUNT", 0),
            note=getattr(orm_model, "NOTE", None),
        )

    def __getattr__(self, name: str):
        lower_name = name.lower()
        if lower_name in {f.name for f in fields(self)}:
            return getattr(self, lower_name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "year": self.year,
            "type": self.type,
            "tmdbid": self.tmdbid,
            "season_count": self.season_count,
            "note": self.note,
        }

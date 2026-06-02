"""
自定义识别词领域实体
对应 CUSTOM_WORDS / CUSTOM_WORD_GROUPS 表
"""

from dataclasses import dataclass, fields
from enum import Enum
from typing import Any, Optional

from app.utils.types import MediaType


class CustomWordType(Enum):
    """识别词类型值对象"""

    BLOCK = 1
    REPLACE = 2
    REPLACE_OFFSET = 3
    OFFSET = 4

    @classmethod
    def from_value(cls, value: int) -> "CustomWordType":
        for member in cls:
            if member.value == value:
                return member
        return cls.BLOCK

    @property
    def display_name(self) -> str:
        return {
            1: "屏蔽",
            2: "替换",
            3: "替换+偏移",
            4: "集偏移",
        }.get(self.value, "未知")


class WordGroupType(Enum):
    """词组类型值对象"""

    MOVIE = 1
    TV = 2

    @classmethod
    def from_value(cls, value: int) -> "WordGroupType":
        for member in cls:
            if member.value == value:
                return member
        return cls.MOVIE

    @property
    def display_name(self) -> str:
        if self == WordGroupType.MOVIE:
            return MediaType.MOVIE.display_name
        if self == WordGroupType.TV:
            return MediaType.TV.display_name
        return "未知"


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

    @property
    def word_type(self) -> CustomWordType:
        return CustomWordType.from_value(self.type)

    @property
    def is_enabled(self) -> bool:
        return bool(self.enabled)

    @property
    def is_block(self) -> bool:
        return self.type == CustomWordType.BLOCK.value

    @property
    def is_replace(self) -> bool:
        return self.type in (CustomWordType.REPLACE.value, CustomWordType.REPLACE_OFFSET.value)

    @property
    def is_offset(self) -> bool:
        return self.type in (CustomWordType.OFFSET.value, CustomWordType.REPLACE_OFFSET.value)

    @property
    def uses_regex(self) -> bool:
        return bool(self.regex)

    @property
    def is_global(self) -> bool:
        """是否为全局词（group_id <= 0）"""
        return self.group_id <= 0

    @property
    def has_replaced(self) -> bool:
        return bool(self.replaced)

    @property
    def has_front_back(self) -> bool:
        return bool(self.front) and bool(self.back)

    @property
    def is_valid(self) -> bool:
        """识别词配置是否有效"""
        if self.is_block or self.is_replace:
            return self.has_replaced
        if self.is_offset:
            return self.has_front_back
        return False

    def validate_offset(self) -> str | None:
        """验证偏移量格式，返回错误信息或 None"""
        if not self.is_offset:
            return None
        if not self.offset:
            return "偏移集数格式有误"
        if "EP" not in self.offset:
            return "偏移集数格式有误"
        import re

        cleaned = re.sub(r"EP", "", self.offset)
        if re.search(r"[^-+*/0-9]", cleaned):
            return "偏移集数格式有误"
        return None

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

    @property
    def group_type(self) -> WordGroupType:
        return WordGroupType.from_value(self.type)

    @property
    def is_movie(self) -> bool:
        return self.type == WordGroupType.MOVIE.value

    @property
    def is_tv(self) -> bool:
        return self.type == WordGroupType.TV.value

    @property
    def has_tmdb(self) -> bool:
        return bool(self.tmdbid)

    @property
    def is_global(self) -> bool:
        """是否为全局词组（tmdbid <= 0）"""
        return self.tmdbid <= 0

    @property
    def display_title(self) -> str:
        """展示标题"""
        parts = [self.title or "未命名"]
        if self.year:
            parts.append(f"({self.year})")
        return " ".join(parts)

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

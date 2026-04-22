# -*- coding: utf-8 -*-
"""
配置领域实体
包含消息客户端、下载器、过滤规则、媒体服务器等配置实体
"""
from dataclasses import dataclass, fields
from typing import Any, Dict, List, Optional


@dataclass
class MessageClientEntity:
    """消息客户端实体"""
    id: int
    name: str
    type: str
    config: str
    switchs: str
    interactive: bool
    enabled: bool
    note: Optional[str]
    templates: Optional[str]

    @classmethod
    def from_orm(cls, orm_model) -> Optional["MessageClientEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            name=orm_model.NAME or "",
            type=orm_model.TYPE or "",
            config=orm_model.CONFIG or "",
            switchs=orm_model.SWITCHS or "",
            interactive=bool(orm_model.INTERACTIVE),
            enabled=bool(orm_model.ENABLED),
            note=orm_model.NOTE,
            templates=getattr(orm_model, 'TEMPLATES', None)
        )

    _ORM_FIELD_MAP = {}

    def __getattr__(self, name: str):
        """兼容旧代码的大写属性访问"""
        lower_name = name.lower()
        field_name = self._ORM_FIELD_MAP.get(lower_name, lower_name)
        if field_name in {f.name for f in fields(self)}:
            return getattr(self, field_name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "config": self.config,
            "switchs": self.switchs,
            "interactive": self.interactive,
            "enabled": self.enabled,
            "note": self.note,
            "templates": self.templates,
        }


@dataclass
class DownloaderEntity:
    """下载器实体"""
    id: int
    name: str
    type: str
    config: str
    transfer: str
    only_nastool: bool
    match_path: bool
    enabled: bool

    @classmethod
    def from_orm(cls, orm_model) -> Optional["DownloaderEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            name=orm_model.NAME or "",
            type=orm_model.TYPE or "",
            config=orm_model.CONFIG or "",
            transfer=orm_model.TRANSFER or "",
            only_nastool=bool(orm_model.ONLY_NASTOOL),
            match_path=bool(orm_model.MATCH_PATH),
            enabled=bool(orm_model.ENABLED)
        )

    _ORM_FIELD_MAP = {}

    def __getattr__(self, name: str):
        """兼容旧代码的大写属性访问"""
        lower_name = name.lower()
        field_name = self._ORM_FIELD_MAP.get(lower_name, lower_name)
        if field_name in {f.name for f in fields(self)}:
            return getattr(self, field_name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "config": self.config,
            "transfer": self.transfer,
            "only_nastool": self.only_nastool,
            "match_path": self.match_path,
            "enabled": self.enabled,
        }


@dataclass
class FilterGroupEntity:
    """过滤规则组实体"""
    id: int
    name: str
    default: bool
    create_time: Optional[str]
    update_time: Optional[str]

    @classmethod
    def from_orm(cls, orm_model) -> Optional["FilterGroupEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            name=orm_model.NAME or "",
            default=bool(orm_model.IS_DEFAULT),
            create_time=orm_model.CREATE_TIME,
            update_time=orm_model.UPDATE_TIME
        )

    _ORM_FIELD_MAP = {
        'is_default': 'default',
    }

    def __getattr__(self, name: str):
        """兼容旧代码的大写属性访问"""
        lower_name = name.lower()
        field_name = self._ORM_FIELD_MAP.get(lower_name, lower_name)
        if field_name in {f.name for f in fields(self)}:
            return getattr(self, field_name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "default": self.default,
            "create_time": self.create_time,
            "update_time": self.update_time,
        }


@dataclass
class FilterRuleEntity:
    """过滤规则实体"""
    id: int
    group_id: int
    name: str
    include: str
    exclude: str
    note: Optional[str]
    priority: int
    create_time: Optional[str]
    update_time: Optional[str]

    @classmethod
    def from_orm(cls, orm_model) -> Optional["FilterRuleEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            group_id=orm_model.GROUP_ID or 0,
            name=orm_model.NAME or "",
            include=orm_model.INCLUDE or "",
            exclude=orm_model.EXCLUDE or "",
            note=orm_model.NOTE,
            priority=orm_model.PRIORITY or 0,
            create_time=orm_model.CREATE_TIME,
            update_time=orm_model.UPDATE_TIME
        )

    _ORM_FIELD_MAP = {}

    def __getattr__(self, name: str):
        """兼容旧代码的大写属性访问"""
        lower_name = name.lower()
        field_name = self._ORM_FIELD_MAP.get(lower_name, lower_name)
        if field_name in {f.name for f in fields(self)}:
            return getattr(self, field_name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "group_id": self.group_id,
            "name": self.name,
            "include": self.include,
            "exclude": self.exclude,
            "note": self.note,
            "priority": self.priority,
            "create_time": self.create_time,
            "update_time": self.update_time,
        }


@dataclass
class MediaServerEntity:
    """媒体服务器实体"""
    id: int
    name: str
    type: str
    config: str
    enabled: bool

    @classmethod
    def from_orm(cls, orm_model) -> Optional["MediaServerEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            name=orm_model.NAME or "",
            type=orm_model.TYPE or "",
            config=orm_model.CONFIG or "",
            enabled=bool(orm_model.ENABLED)
        )

    _ORM_FIELD_MAP = {}

    def __getattr__(self, name: str):
        """兼容旧代码的大写属性访问"""
        lower_name = name.lower()
        field_name = self._ORM_FIELD_MAP.get(lower_name, lower_name)
        if field_name in {f.name for f in fields(self)}:
            return getattr(self, field_name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "config": self.config,
            "enabled": self.enabled,
        }


@dataclass
class TorrentRemoveTaskEntity:
    """自动删种任务实体"""
    id: int
    name: str
    downloader: str
    config: str
    enabled: bool

    @classmethod
    def from_orm(cls, orm_model) -> Optional["TorrentRemoveTaskEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            name=orm_model.NAME or "",
            downloader=orm_model.DOWNLOADER or "",
            config=orm_model.CONFIG or "",
            enabled=bool(orm_model.ENABLED)
        )

    _ORM_FIELD_MAP = {}

    def __getattr__(self, name: str):
        """兼容旧代码的大写属性访问"""
        lower_name = name.lower()
        field_name = self._ORM_FIELD_MAP.get(lower_name, lower_name)
        if field_name in {f.name for f in fields(self)}:
            return getattr(self, field_name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "downloader": self.downloader,
            "config": self.config,
            "enabled": self.enabled,
        }

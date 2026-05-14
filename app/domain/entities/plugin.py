"""
插件历史 / TMDB黑名单领域实体 / 插件框架v2实体
对应 PLUGIN_HISTORY / TMDB_BLACKLIST / PLUGIN_MANIFEST / PLUGIN_CONFIG / PLUGIN_LOGS 表
"""
from dataclasses import dataclass, field, fields
from typing import Any, Optional


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

    def to_dict(self) -> dict[str, Any]:
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
    title: str | None
    year: str | None
    media_type: str | None
    poster_path: str | None
    backdrop_path: str | None
    note: str | None

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

    def to_dict(self) -> dict[str, Any]:
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


@dataclass
class PluginManifestEntity:
    """插件框架v2 - 插件清单实体"""
    id: str
    name: str
    version: str
    author: str = ""
    description: str = ""
    category: str = "tool"
    tags: list[str] = field(default_factory=list)
    icon: str = ""
    color: str = ""
    manifest_json: str = ""
    installed_at: str | None = None
    updated_at: str | None = None
    enabled: bool = False
    installed: bool = True
    path: str = ""

    @classmethod
    def from_orm(cls, orm_model) -> Optional["PluginManifestEntity"]:
        if orm_model is None:
            return None
        import json
        tags = []
        try:
            tags = json.loads(orm_model.TAGS or "[]")
        except Exception:
            pass
        return cls(
            id=orm_model.ID or "",
            name=orm_model.NAME or "",
            version=orm_model.VERSION or "",
            author=orm_model.AUTHOR or "",
            description=orm_model.DESCRIPTION or "",
            category=orm_model.CATEGORY or "tool",
            tags=tags,
            icon=orm_model.ICON or "",
            color=orm_model.COLOR or "",
            manifest_json=orm_model.MANIFEST_JSON or "",
            installed_at=orm_model.INSTALLED_AT,
            updated_at=orm_model.UPDATED_AT,
            enabled=bool(orm_model.ENABLED),
            installed=bool(getattr(orm_model, 'INSTALLED', True)),
            path=orm_model.PATH or "",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "category": self.category,
            "tags": self.tags,
            "icon": self.icon,
            "color": self.color,
            "enabled": self.enabled,
            "path": self.path,
        }


@dataclass
class PluginConfigEntity:
    """插件框架v2 - 插件配置实体"""
    plugin_id: str
    config: dict[str, Any] = field(default_factory=dict)
    updated_at: str | None = None

    @classmethod
    def from_orm(cls, orm_model) -> Optional["PluginConfigEntity"]:
        if orm_model is None:
            return None
        import json
        cfg = {}
        try:
            cfg = json.loads(orm_model.CONFIG or "{}")
        except Exception:
            pass
        return cls(
            plugin_id=orm_model.PLUGIN_ID or "",
            config=cfg,
            updated_at=orm_model.UPDATED_AT,
        )


@dataclass
class PluginLogEntity:
    """插件框架v2 - 插件日志实体"""
    id: int
    plugin_id: str
    level: str
    message: str
    created_at: str | None = None

    @classmethod
    def from_orm(cls, orm_model) -> Optional["PluginLogEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            plugin_id=orm_model.PLUGIN_ID or "",
            level=orm_model.LEVEL or "",
            message=orm_model.MESSAGE or "",
            created_at=orm_model.CREATED_AT,
        )

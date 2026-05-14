"""
同步领域实体
包含目录同步配置实体
"""

from dataclasses import dataclass, fields
from typing import Any, Optional


@dataclass
class SyncPathEntity:
    """目录同步路径实体"""

    id: int
    source: str
    dest: str
    unknown: str
    mode: str
    compatibility: bool
    rename: bool
    enabled: bool
    note: str | None

    @classmethod
    def from_orm(cls, orm_model) -> Optional["SyncPathEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            source=orm_model.SOURCE or "",
            dest=orm_model.DEST or "",
            unknown=orm_model.UNKNOWN or "",
            mode=orm_model.MODE or "",
            compatibility=bool(orm_model.COMPATIBILITY),
            rename=bool(orm_model.RENAME),
            enabled=bool(orm_model.ENABLED),
            note=orm_model.NOTE,
        )

    _ORM_FIELD_MAP = {}

    def __getattr__(self, name: str):
        """兼容旧代码的大写属性访问"""
        lower_name = name.lower()
        field_name = self._ORM_FIELD_MAP.get(lower_name, lower_name)
        if field_name in {f.name for f in fields(self)}:
            return getattr(self, field_name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "dest": self.dest,
            "unknown": self.unknown,
            "mode": self.mode,
            "compatibility": self.compatibility,
            "rename": self.rename,
            "enabled": self.enabled,
            "note": self.note,
        }

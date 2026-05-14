"""
系统字典领域实体
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class SystemDictEntity:
    """系统字典实体"""

    id: int
    type: str
    key: str
    value: str
    note: str | None

    @classmethod
    def from_orm(cls, orm_model) -> Optional["SystemDictEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=getattr(orm_model, "ID", 0),
            type=getattr(orm_model, "TYPE", ""),
            key=getattr(orm_model, "KEY", ""),
            value=getattr(orm_model, "VALUE", ""),
            note=getattr(orm_model, "NOTE", None),
        )

"""
存储后端领域实体
"""

import json
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class StorageBackendEntity:
    """存储后端配置实体"""

    id: int
    name: str
    type: str
    config: dict[str, Any]
    enabled: bool

    @classmethod
    def from_orm(cls, orm_model) -> Optional["StorageBackendEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            name=orm_model.NAME or "",
            type=orm_model.TYPE or "",
            config=json.loads(orm_model.CONFIG or "{}"),
            enabled=bool(orm_model.ENABLED),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "config": self.config,
            "enabled": self.enabled,
        }

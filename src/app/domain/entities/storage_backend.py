"""
存储后端领域实体
"""

from dataclasses import dataclass
from typing import Any, Optional

from app.utils.json_utils import JsonUtils


@dataclass
class StorageBackendEntity:
    """存储后端配置实体"""

    id: int
    name: str
    type: str
    config: dict[str, Any]
    enabled: bool

    @property
    def is_available(self) -> bool:
        """存储后端是否可用"""
        return self.enabled and bool(self.type)

    @property
    def is_local(self) -> bool:
        """是否为本地存储"""
        return self.type == "local"

    @property
    def is_remote(self) -> bool:
        """是否为远程存储"""
        return not self.is_local

    def get_config_value(self, key: str, default: Any = None) -> Any:
        """获取配置项值"""
        return self.config.get(key, default)

    @classmethod
    def from_orm(cls, orm_model) -> Optional["StorageBackendEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            name=orm_model.NAME or "",
            type=orm_model.TYPE or "",
            config=JsonUtils.loads(orm_model.CONFIG or "{}"),
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

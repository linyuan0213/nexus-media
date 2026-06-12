"""分类配置领域实体"""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class CategoryConfigEntity:
    """二级分类配置实体"""

    id: int
    media_type: str
    name: str
    sort_order: int
    is_default: bool
    rules: dict[str, str]

    @classmethod
    def from_orm(cls, orm_model, rules: dict[str, str] | None = None) -> Optional["CategoryConfigEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            media_type=orm_model.MEDIA_TYPE or "",
            name=orm_model.NAME or "",
            sort_order=int(orm_model.SORT_ORDER or 0),
            is_default=bool(orm_model.IS_DEFAULT),
            rules=rules or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "media_type": self.media_type,
            "name": self.name,
            "sort_order": self.sort_order,
            "is_default": self.is_default,
            "rules": self.rules,
        }

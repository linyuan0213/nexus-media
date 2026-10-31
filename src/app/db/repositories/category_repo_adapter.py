"""分类配置领域 Repository 适配器"""

from __future__ import annotations

import json
from typing import Any

from app.db.repositories.config_repository import ConfigRepository
from app.domain.entities.category import CategoryConfigEntity
from app.domain.interfaces.category_repo import ICategoryConfigRepository


class CategoryConfigRepositoryAdapter(ICategoryConfigRepository):
    """二级分类配置仓储适配器"""

    def __init__(self, repo: ConfigRepository | None = None):
        self._repo = repo or ConfigRepository()

    def get_all(self) -> list[CategoryConfigEntity]:
        categories = self._repo.get_category_configs()
        rules = self._repo.get_category_rules()
        rule_map: dict[int, dict[str, str] | list[dict[str, Any]]] = {}
        for rule in rules:
            raw_json = getattr(rule, "RULE_JSON", None)
            if raw_json:
                try:
                    parsed = json.loads(str(raw_json))
                except (TypeError, ValueError):
                    continue
                if isinstance(parsed, dict):
                    rule_map.setdefault(rule.CATEGORY_ID, []).append(parsed)  # type: ignore[union-attr]
            else:
                rule_map.setdefault(rule.CATEGORY_ID, {})[rule.FIELD] = rule.VALUE  # type: ignore[index]
        return [
            entity
            for entity in [CategoryConfigEntity.from_orm(c, rule_map.get(c.ID, {})) for c in categories]
            if entity is not None
        ]

    def save(
        self,
        media_type: str,
        name: str,
        sort_order: int,
        is_default: int,
        rules: dict[str, str] | list[dict[str, Any]],
        enabled: int = 1,
    ) -> int:
        return self._repo.save_category_config(media_type, name, sort_order, is_default, rules, enabled)

    def delete(self, cid: int) -> None:
        self._repo.delete_category_config(cid)

    def clear_all(self) -> None:
        self._repo.clear_category_configs()

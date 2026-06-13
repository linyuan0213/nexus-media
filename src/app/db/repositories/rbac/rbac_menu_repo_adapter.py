"""
RBAC 领域 Repository 适配器
将旧版 RBACRepository 适配为新领域接口
"""

from typing import Any, cast

from app.db.repositories.rbac.rbac_menu_repository import RBACMenuRepository
from app.domain.entities.rbac import (
    RBACMenuEntity,
)
from app.domain.interfaces.rbac_repo import (
    IRBACMenuRepository,
)


class RBACMenuRepositoryAdapter(IRBACMenuRepository):
    """RBAC菜单仓储适配器"""

    def __init__(self, repo: RBACMenuRepository | None = None):
        self._repo = repo or RBACMenuRepository()

    def get_menu_by_id(self, menu_id: int) -> RBACMenuEntity | None:
        row = self._repo.get_menu_by_id(menu_id)
        return RBACMenuEntity.from_orm(row)

    def get_menu_by_code(self, menu_code: str, include_hidden: bool = True) -> RBACMenuEntity | None:
        row = self._repo.get_menu_by_code(menu_code, include_hidden=include_hidden)
        return RBACMenuEntity.from_orm(row)

    def get_all_menus(self, status: int | None = None) -> list[RBACMenuEntity]:
        rows = self._repo.get_all_menus(status=status)
        return [e for e in [RBACMenuEntity.from_orm(r) for r in rows] if e is not None]

    def get_top_menus(self, include_hidden: bool = False) -> list[RBACMenuEntity]:
        rows = self._repo.get_top_menus(include_hidden=include_hidden)
        return [e for e in [RBACMenuEntity.from_orm(r) for r in rows] if e is not None]

    def get_children_menus(self, parent_id: int) -> list[RBACMenuEntity]:
        rows = self._repo.get_children_menus(parent_id)
        return [e for e in [RBACMenuEntity.from_orm(r) for r in rows] if e is not None]

    def get_menu_tree(self, include_hidden: bool = False) -> list[dict[str, Any]]:
        return self._repo.get_menu_tree(include_hidden=include_hidden)

    def get_user_menus(self, user_id: int) -> list[RBACMenuEntity]:
        rows = self._repo.get_user_menus(user_id)
        return [e for e in [RBACMenuEntity.from_orm(r) for r in rows] if e is not None]

    def create_menu(
        self,
        menu_name: str,
        menu_code: str,
        parent_id: int | None = None,
        path: str | None = None,
        icon: str | None = None,
        component: str | None = None,
        sort_order: int = 0,
        menu_level: int = 1,
        permission_code: str | None = None,
        **kwargs,
    ) -> RBACMenuEntity:
        row = self._repo.create_menu(
            menu_name, menu_code, parent_id, path, icon, component, sort_order, menu_level, permission_code, **kwargs
        )
        if isinstance(row, bool):
            row = self._repo.get_menu_by_code(menu_code)
        return cast(RBACMenuEntity, RBACMenuEntity.from_orm(row))

    def update_menu(self, menu_id: int, **kwargs) -> bool:
        return self._repo.update_menu(menu_id, **kwargs)

    def delete_menu(self, menu_id: int) -> bool:
        return self._repo.delete_menu(menu_id)

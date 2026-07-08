"""
RBAC Repository
基于角色的访问控制(RBAC)数据访问层
处理用户、角色、权限、菜单的数据库操作
"""

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models.rbac import (
    RBACMenu,
    role_menus,
    user_roles,
)
from app.db.repositories.base_repository import BaseRepository


class RBACMenuRepository(BaseRepository):
    """
    RBAC菜单管理仓储
    """

    def _get_menu_by_id(self, db: Session, menu_id: int) -> RBACMenu | None:
        """在同一 session 内根据ID获取菜单。"""
        return db.query(RBACMenu).filter(RBACMenu.ID == menu_id).first()

    def get_menu_by_id(self, menu_id: int) -> RBACMenu | None:
        """
        根据ID获取菜单
        """
        with self.session() as db:
            return self._get_menu_by_id(db, menu_id)

    def get_menu_by_code(self, menu_code: str, include_hidden: bool = True) -> RBACMenu | None:
        """
        根据菜单代码获取菜单

        Args:
            menu_code: 菜单代码
            include_hidden: 是否包含隐藏的菜单，默认包含
        """
        with self.session() as db:
            query = db.query(RBACMenu).filter(RBACMenu.MENU_CODE == menu_code)
            if not include_hidden:
                query = query.filter(RBACMenu.STATUS == 1)
            return query.first()

    def get_all_menus(self, status: int | None = None) -> list[RBACMenu]:
        """
        获取所有菜单
        """
        with self.session() as db:
            query = db.query(RBACMenu)
            if status is not None:
                query = query.filter(RBACMenu.STATUS == status)
            return query.order_by(RBACMenu.SORT_ORDER).all()

    def get_top_menus(self, include_hidden: bool = False) -> list[RBACMenu]:
        """
        获取顶级菜单列表

        Args:
            include_hidden: 是否包含隐藏的菜单
        """
        with self.session() as db:
            query = db.query(RBACMenu).filter(RBACMenu.PARENT_ID.is_(None))
            if not include_hidden:
                query = query.filter(RBACMenu.STATUS == 1)
            return query.order_by(RBACMenu.SORT_ORDER).all()

    def get_children_menus(self, parent_id: int) -> list[RBACMenu]:
        """
        获取子菜单列表
        """
        with self.session() as db:
            return (
                db.query(RBACMenu)
                .filter(RBACMenu.PARENT_ID == parent_id, RBACMenu.STATUS == 1)
                .order_by(RBACMenu.SORT_ORDER)
                .all()
            )

    def get_menu_tree(self, include_hidden: bool = False) -> list[dict[str, Any]]:
        """
        获取菜单树形结构

        Args:
            include_hidden: 是否包含隐藏的菜单
        """

        def build_tree(parent_id, db: Session):
            query = db.query(RBACMenu).filter(
                RBACMenu.PARENT_ID == parent_id if parent_id is not None else RBACMenu.PARENT_ID.is_(None)
            )
            if not include_hidden:
                query = query.filter(RBACMenu.STATUS == 1)
            menus = query.order_by(RBACMenu.SORT_ORDER).all()

            result = []
            for menu in menus:
                menu_dict = menu.to_dict()
                menu_dict["children"] = build_tree(menu.ID, db)
                result.append(menu_dict)
            return result

        with self.session() as db:
            return build_tree(None, db)

    def get_user_menus(self, user_id: int) -> list[RBACMenu]:
        """
        获取用户可访问的菜单列表

        通过用户的角色关联获取菜单
        """
        with self.session() as db:
            menus = (
                db.query(RBACMenu)
                .join(role_menus, role_menus.c.menu_id == RBACMenu.ID)
                .join(user_roles, role_menus.c.role_id == user_roles.c.role_id)
                .filter(user_roles.c.user_id == user_id)
                .distinct()
                .order_by(RBACMenu.SORT_ORDER)
                .all()
            )

            return menus

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
    ) -> RBACMenu:
        """
        创建菜单
        """
        with self.session() as db:
            menu = RBACMenu(
                MENU_NAME=menu_name,
                MENU_CODE=menu_code,
                PARENT_ID=parent_id,
                PATH=path,
                ICON=icon,
                COMPONENT=component,
                SORT_ORDER=sort_order,
                MENU_LEVEL=menu_level,
                PERMISSION_CODE=permission_code,
                STATUS=1,
            )
            # 支持 Vben 扩展字段
            vben_fields = [
                "REDIRECT",
                "KEEP_ALIVE",
                "AFFIX_TAB",
                "HIDE_IN_MENU",
                "HIDE_IN_TAB",
                "HIDE_IN_BREADCRUMB",
                "ACTIVE_ICON",
                "BADGE",
                "BADGE_TYPE",
                "IS_BUILTIN",
            ]
            for key, value in kwargs.items():
                if key.upper() in vben_fields:
                    setattr(menu, key.upper(), value)
            db.add(menu)
            db.commit()
            return menu

    def update_menu(self, menu_id: int, **kwargs) -> bool:
        """
        更新菜单信息
        """
        with self.session() as db:
            menu = self._get_menu_by_id(db, menu_id)
            if not menu:
                return False

            allowed_fields = [
                "MENU_NAME",
                "MENU_CODE",
                "PATH",
                "ICON",
                "COMPONENT",
                "PARENT_ID",
                "SORT_ORDER",
                "IS_HIDDEN",
                "STATUS",
                "PERMISSION_CODE",
                "REDIRECT",
                "KEEP_ALIVE",
                "AFFIX_TAB",
                "HIDE_IN_MENU",
                "HIDE_IN_TAB",
                "HIDE_IN_BREADCRUMB",
                "ACTIVE_ICON",
                "BADGE",
                "BADGE_TYPE",
                "IS_BUILTIN",
            ]
            for key, value in kwargs.items():
                if key.upper() in allowed_fields:
                    setattr(menu, key.upper(), value)

            # 更新菜单层级
            if "parent_id" in kwargs:
                if kwargs["parent_id"] is None:
                    menu.MENU_LEVEL = 1  # type: ignore[assignment]
                else:
                    parent = self._get_menu_by_id(db, kwargs["parent_id"])
                    if parent:
                        menu.MENU_LEVEL = parent.MENU_LEVEL + 1  # type: ignore[assignment]

            menu.UPDATED_AT = datetime.now()  # type: ignore[assignment]
            db.commit()
            return True

    def delete_menu(self, menu_id: int) -> bool:
        """
        删除菜单（同时删除子菜单）
        """
        with self.session() as db:
            # 先删除子菜单
            db.query(RBACMenu).filter(RBACMenu.PARENT_ID == menu_id).delete()
            # 删除菜单本身
            result = db.query(RBACMenu).filter(RBACMenu.ID == menu_id).delete()
            db.commit()
            return result > 0

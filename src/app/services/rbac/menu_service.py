"""RBAC menu service - 菜单管理."""

from typing import Any

import log

from app.core.exceptions import ResourceAlreadyExistsError, ResourceNotFoundError


class RBACMenuService:
    """菜单管理服务"""

    def __init__(self, menu_repo, user_repo):
        self.menu_repo = menu_repo
        self.user_repo = user_repo

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
    ):
        """创建菜单，成功返回菜单对象，失败抛出异常."""
        existing = self.menu_repo.get_menu_by_code(menu_code)
        if existing:
            raise ResourceAlreadyExistsError(f"菜单代码已存在: {menu_code}")
        menu = self.menu_repo.create_menu(
            menu_name=menu_name,
            menu_code=menu_code,
            parent_id=parent_id,
            path=path,
            icon=icon,
            component=component,
            sort_order=sort_order,
            menu_level=menu_level,
            permission_code=permission_code,
            **kwargs,
        )
        log.info(f"【RBAC】创建菜单成功: {menu_name}")
        return menu

    def update_menu(self, menu_id: int, **kwargs) -> None:
        """更新菜单，失败抛出异常."""
        menu = self.menu_repo.get_menu_by_id(menu_id)
        if not menu:
            raise ResourceNotFoundError(f"菜单不存在: id={menu_id}")
        success = self.menu_repo.update_menu(menu_id, **kwargs)
        if not success:
            raise ResourceNotFoundError("更新失败")

    def delete_menu(self, menu_id: int) -> None:
        """删除菜单，失败抛出异常."""
        menu = self.menu_repo.get_menu_by_id(menu_id)
        if not menu:
            raise ResourceNotFoundError(f"菜单不存在: id={menu_id}")
        success = self.menu_repo.delete_menu(menu_id)
        if not success:
            raise ResourceNotFoundError("删除失败")
        log.info(f"【RBAC】删除菜单: {menu.MENU_NAME}")

    def get_menu_tree(self, include_hidden: bool = False) -> list[dict[str, Any]]:
        """获取菜单树形结构"""
        return self.menu_repo.get_menu_tree(include_hidden=include_hidden)

    def get_all_menus(self):
        """获取所有菜单"""
        return self.menu_repo.get_all_menus()

    def get_menu_by_id(self, menu_id: int):
        """根据 ID 获取菜单"""
        return self.menu_repo.get_menu_by_id(menu_id)

    def get_user_menus(self, user_id: int) -> list[dict]:
        """获取用户的菜单树（Vben 格式）"""
        user = self.user_repo.get_user_by_id(user_id)
        if user and user.IS_SUPERADMIN == 1:
            menus = self.menu_repo.get_all_menus()
        else:
            menus = self.menu_repo.get_user_menus(user_id)

        menu_ids = {m.ID for m in menus}
        all_menus = list(menus)
        for m in menus:
            pid = m.PARENT_ID
            while pid:
                parent = self.menu_repo.get_menu_by_id(pid)
                if parent and parent.ID not in menu_ids:
                    menu_ids.add(parent.ID)
                    all_menus.append(parent)
                pid = parent.PARENT_ID if parent else None

        all_menus.sort(key=lambda x: x.SORT_ORDER)

        def _to_vben_node(menu):
            meta = {"title": menu.MENU_NAME}
            if menu.ICON:
                meta["icon"] = menu.ICON
            if menu.SORT_ORDER is not None:
                meta["order"] = menu.SORT_ORDER
            if menu.PERMISSION_CODE:
                meta["authority"] = [menu.PERMISSION_CODE]
            if getattr(menu, "HIDE_IN_MENU", 0):
                meta["hideInMenu"] = True
            if getattr(menu, "STATUS", 1) == 0:
                meta["menuVisibleWithForbidden"] = True
            path_val = menu.PATH or menu.MENU_CODE
            node = {
                "path": path_val.lower(),
                "name": menu.MENU_CODE,
                "meta": meta,
            }
            if menu.COMPONENT:
                node["component"] = menu.COMPONENT
            if getattr(menu, "REDIRECT", None):
                node["redirect"] = menu.REDIRECT
            return node

        menu_map = {m.ID: _to_vben_node(m) for m in all_menus}
        pid_map = {}
        for m in all_menus:
            pid = m.PARENT_ID
            if pid not in pid_map:
                pid_map[pid] = []
            pid_map[pid].append(m.ID)

        def _build_tree(parent_id=None, parent_disabled=False):
            result = []
            for mid in pid_map.get(parent_id, []):
                node = dict(menu_map[mid])
                is_disabled = parent_disabled or node.get("meta", {}).get("menuVisibleWithForbidden", False)
                if is_disabled:
                    node.setdefault("meta", {})["menuVisibleWithForbidden"] = True
                children = _build_tree(mid, is_disabled)
                if children:
                    node["children"] = children
                result.append(node)
            return result

        return _build_tree()

"""RBAC 菜单初始化."""

import log
from app.di import container

from app.services.rbac.init.constants import DEFAULT_MENUS


def init_rbac_menus():
    """初始化菜单数据"""
    menu_repo = container.rbac_menu_repo()
    created_count = 0

    def create_menu_recursive(menu_data, parent_id=None):
        nonlocal created_count

        existing = menu_repo.get_menu_by_code(menu_data["code"])
        if not existing:
            result = menu_repo.create_menu(
                menu_name=menu_data["name"],
                menu_code=menu_data["code"],
                parent_id=parent_id,
                path=menu_data.get("path"),
                icon=menu_data.get("icon"),
                component=menu_data.get("component"),
                sort_order=menu_data.get("sort_order", 0),
                menu_level=menu_data.get("level", 1),
                permission_code=menu_data.get("permission_code"),
                hide_in_menu=menu_data.get("hide_in_menu", 0),
            )
            if isinstance(result, bool):
                menu = menu_repo.get_menu_by_code(menu_data["code"])
            else:
                menu = result

            if menu:
                created_count += 1
                log.info(f"[RBAC初始化]创建菜单: {menu_data['name']}")
                menu_id = menu.ID
            else:
                log.error(f"[RBAC初始化]创建菜单失败: {menu_data['name']}")
                return
        else:
            menu_id = existing.ID

        if "children" in menu_data:
            for child_data in menu_data["children"]:
                create_menu_recursive(child_data, menu_id)

    for menu_data in DEFAULT_MENUS:
        create_menu_recursive(menu_data)

    log.info(f"[RBAC初始化]菜单初始化完成，新增 {created_count} 个菜单")
    return created_count

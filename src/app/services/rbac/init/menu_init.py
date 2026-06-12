"""RBAC 菜单初始化.

策略：
1. 收集 DEFAULT_MENUS 中所有菜单 code；
2. 删除数据库中不在该集合内的旧菜单（按 level 降序，先删子后删父）；
3. 递归遍历 DEFAULT_MENUS，已存在则更新属性，不存在则创建。
"""

from typing import Any

import log

from app.services.rbac.init.constants import DEFAULT_MENUS
from app.db.repositories.rbac_repo_adapter import RBACMenuRepositoryAdapter


def init_rbac_menus(menu_repo: Any = None):
    """初始化菜单数据：同步 DEFAULT_MENUS 到数据库"""
    menu_repo = menu_repo or RBACMenuRepositoryAdapter()

    # 1. 收集 DEFAULT_MENUS 中所有 code
    default_codes: set[str] = set()

    def collect_codes(menu_data_list):
        for data in menu_data_list:
            default_codes.add(data["code"])
            if "children" in data:
                collect_codes(data["children"])

    collect_codes(DEFAULT_MENUS)

    # 2. 获取数据库中所有现有菜单，删除不在 DEFAULT_MENUS 中的
    existing_menus = menu_repo.get_all_menus()
    menus_to_delete = [m for m in existing_menus if m.MENU_CODE not in default_codes]
    deleted_count = 0
    # 按 menu_level 降序删除，确保先删子菜单
    for menu in sorted(menus_to_delete, key=lambda m: getattr(m, "MENU_LEVEL", 1), reverse=True):
        try:
            menu_repo.delete_menu(menu.ID)
            deleted_count += 1
            log.info(f"[RBAC初始化]删除旧菜单: {menu.MENU_NAME} ({menu.MENU_CODE})")
        except Exception as e:
            log.warn(f"[RBAC初始化]删除旧菜单失败: {menu.MENU_CODE} - {e}")

    # 3. 递归创建/更新菜单
    created_count = 0
    updated_count = 0

    def sync_menu_recursive(menu_data, parent_id=None):
        nonlocal created_count, updated_count

        existing = menu_repo.get_menu_by_code(menu_data["code"])
        if existing:
            # 更新已有菜单
            updates: dict = {}
            if existing.MENU_NAME != menu_data["name"]:
                updates["menu_name"] = menu_data["name"]
            if existing.PATH != menu_data.get("path"):
                updates["path"] = menu_data.get("path")
            if existing.ICON != menu_data.get("icon"):
                updates["icon"] = menu_data.get("icon")
            if existing.COMPONENT != menu_data.get("component"):
                updates["component"] = menu_data.get("component")
            if existing.SORT_ORDER != menu_data.get("sort_order", 0):
                updates["sort_order"] = menu_data.get("sort_order", 0)
            if existing.MENU_LEVEL != menu_data.get("level", 1):
                updates["menu_level"] = menu_data.get("level", 1)
            if getattr(existing, "PERMISSION_CODE", None) != menu_data.get("permission_code"):
                updates["permission_code"] = menu_data.get("permission_code")
            if getattr(existing, "HIDE_IN_MENU", 0) != menu_data.get("hide_in_menu", 0):
                updates["hide_in_menu"] = menu_data.get("hide_in_menu", 0)
            if existing.PARENT_ID != parent_id:
                updates["parent_id"] = parent_id

            if updates:
                try:
                    menu_repo.update_menu(existing.ID, **updates)
                    updated_count += 1
                    log.info(f"[RBAC初始化]更新菜单: {menu_data['name']}")
                except Exception as e:
                    log.warn(f"[RBAC初始化]更新菜单失败: {menu_data['name']} - {e}")
            menu_id = existing.ID
        else:
            # 创建新菜单
            try:
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
            except Exception as e:
                log.error(f"[RBAC初始化]创建菜单失败: {menu_data['name']} - {e}")
                return

        if "children" in menu_data:
            for child_data in menu_data["children"]:
                sync_menu_recursive(child_data, menu_id)

    for menu_data in DEFAULT_MENUS:
        sync_menu_recursive(menu_data)

    log.info(f"[RBAC初始化]菜单同步完成，新增 {created_count} 个，更新 {updated_count} 个，删除 {deleted_count} 个")
    return created_count + updated_count

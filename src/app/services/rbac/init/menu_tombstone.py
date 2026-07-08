"""内置菜单墓碑（tombstone）.

用户手动删除的内置(默认)菜单会记录到 SYSTEM_DICT，启动初始化时跳过重建，
从而实现「删除内置菜单后重启不恢复」。若同 code 的菜单再次出现（用户手动重建），
则清除对应墓碑。
"""

from typing import Any

from app.db.repositories.system_dict_repository import SystemDictRepository

TOMBSTONE_TYPE = "menu_tombstone"


def add_menu_tombstone(code: str, repo: Any = None) -> None:
    if not code:
        return
    (repo or SystemDictRepository()).set(TOMBSTONE_TYPE, code, "1", note="用户删除的内置菜单")


def remove_menu_tombstone(code: str, repo: Any = None) -> None:
    if not code:
        return
    (repo or SystemDictRepository()).delete(TOMBSTONE_TYPE, code)


def get_menu_tombstones(repo: Any = None) -> set[str]:
    rows = (repo or SystemDictRepository()).list_by_type(TOMBSTONE_TYPE)
    return {r.KEY for r in rows if r.KEY}


def clear_all_menu_tombstones(repo: Any = None) -> int:
    """清空所有菜单墓碑，返回清除数量。用于「重置菜单」。"""
    repo = repo or SystemDictRepository()
    rows = repo.list_by_type(TOMBSTONE_TYPE)
    count = 0
    for r in rows:
        if r.KEY:
            repo.delete(TOMBSTONE_TYPE, r.KEY)
            count += 1
    return count

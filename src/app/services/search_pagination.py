"""
搜索分页管理模块
管理消息中心搜索结果的缓存和分页导航
"""

from typing import Any

from app.message import Message
from app.utils import StringUtils


class SearchPaginationManager:
    """搜索分页管理器"""

    _PAGE_SIZE = 8

    def __init__(self):
        self._cache: dict[str, dict] = {}
        self._media_cache: dict[str, list] = {}
        self._media_type: dict[str, str] = {}

    def set_media_cache(self, user_id: str, media_list: list, media_type: str = "SEARCH"):
        """设置媒体识别缓存"""
        self._media_cache[user_id] = media_list
        self._media_type[user_id] = media_type

    def get_media_cache(self, user_id: str) -> list | None:
        return self._media_cache.get(user_id)

    def get_media_type(self, user_id: str) -> str:
        return self._media_type.get(user_id, "SEARCH")

    def clear_media_cache(self, user_id: str):
        self._media_cache.pop(user_id, None)
        self._media_type.pop(user_id, None)
        self._cache.pop(user_id, None)

    def set_search_results(self, user_id: str, results: list, title: str = "搜索结果"):
        """设置搜索结果分页缓存"""
        self._cache[user_id] = {
            "page": 1,
            "page_size": self._PAGE_SIZE,
            "total": len(results),
            "all_items": results,
            "media_title": title,
        }

    def get_page(self, user_id: str) -> dict | None:
        return self._cache.get(user_id)

    def has_page(self, user_id: str) -> bool:
        return user_id in self._cache

    def navigate(self, user_id: str, direction: str) -> dict | None:
        """分页导航：n=下一页, p=上一页"""
        page_info = self._cache.get(user_id)
        if not page_info:
            return None

        current = page_info["page"]
        size = page_info["page_size"]
        total = page_info["total"]
        max_page = ((total - 1) // size) + 1

        if direction == "n":
            if current >= max_page:
                return {"error": "已经是最后一页了"}
            page_info["page"] = current + 1
        elif direction == "p":
            if current <= 1:
                return {"error": "已经是第一页了"}
            page_info["page"] = current - 1
        else:
            return None

        return self._get_current_page(user_id)

    def select_item(self, user_id: str, index: int) -> Any | None:
        """选择指定序号的条目（1-based）"""
        page_info = self._cache.get(user_id)
        if not page_info:
            return None
        current = page_info["page"]
        size = page_info["page_size"]
        items = page_info["all_items"]
        item_idx = (current - 1) * size + (index - 1)
        if 0 <= item_idx < len(items):
            return items[item_idx]
        return None

    def get_current_page_items(self, user_id: str) -> dict | None:
        return self._get_current_page(user_id)

    def _get_current_page(self, user_id: str) -> dict | None:
        page_info = self._cache.get(user_id)
        if not page_info:
            return None
        current = page_info["page"]
        size = page_info["page_size"]
        items = page_info["all_items"]
        total = page_info["total"]
        max_page = ((total - 1) // size) + 1

        start = (current - 1) * size
        end = min(start + size, total)
        return {
            "items": items[start:end],
            "page": current,
            "total_pages": max_page,
            "total": total,
            "title": page_info["media_title"],
        }

    def send_page_message(self, channel, user_id: str):
        """发送分页结果消息"""
        result = self._get_current_page(user_id)
        if not result:
            Message().send_channel_msg(channel=channel, title="没有可用的搜索结果分页", user_id=user_id)
            return

        items = result["items"]
        page = result["page"]
        total_pages = result["total_pages"]
        title = result["title"]
        size = len(items)

        lines = []
        for i, item in enumerate(items, 1):
            name = getattr(item, "TORRENT_NAME", None) or getattr(item, "TITLE", None) or "未知标题"
            size_str = f"，大小: {StringUtils.str_filesize(item.SIZE)}" if hasattr(item, "SIZE") and item.SIZE else ""
            seeders_str = f"，做种: {item.SEEDERS}" if hasattr(item, "SEEDERS") and item.SEEDERS else ""
            site_str = f"，站点: {item.SITE}" if hasattr(item, "SITE") and item.SITE else ""
            lines.append(f"{i}. {name}{size_str}{seeders_str}{site_str}")

        msg_title = f"{title} 第{page}页，共{total_pages}页"
        if total_pages > 1:
            msg_title += "\n输入 n 查看下一页，p 查看上一页"
        msg_title += f"\n输入 1-{size} 选择下载对应资源"

        Message().send_channel_msg(channel=channel, title=msg_title, text="\n".join(lines), user_id=user_id)


# 全局分页管理器实例
pagination_mgr = SearchPaginationManager()

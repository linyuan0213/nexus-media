"""Subscribe utils - 订阅模块共享工具函数."""

from typing import Any

from app.utils.json_utils import JsonUtils


def parse_rss_desc(desc):
    """解析订阅的JSON字段"""
    if not desc:
        return {}
    return JsonUtils.loads(desc) or {}


def gen_rss_note(media: Any) -> str:
    """生成订阅的JSON备注信息"""
    if not media:
        return "{}"
    note = {"poster": media.get_poster_image(), "release_date": media.release_date, "vote": media.vote_average}
    return JsonUtils.dumps(note, separators=(", ", ": "))

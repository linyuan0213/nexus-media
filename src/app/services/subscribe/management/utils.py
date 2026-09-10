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


def tv_filter_signature(row) -> tuple:
    """订阅过滤要求签名（实体/模型字段名兼容）.

    用于判断兄弟订阅能否共享同一下载/进度：质量/规则/免费等要求一致才联动。
    """

    def g(name):
        val = getattr(row, name, None)
        if val is None:
            val = getattr(row, name.upper(), None)
        return val

    return (
        g("filter_restype") or "",
        g("filter_pix") or "",
        g("filter_team") or "",
        str(g("filter_rule") or ""),
        g("filter_include") or "",
        g("filter_exclude") or "",
        str(g("filter_free") if g("filter_free") is not None else ""),
    )

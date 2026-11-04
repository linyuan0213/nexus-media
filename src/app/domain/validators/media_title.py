"""媒体标题领域校验器 — 过滤无效/垃圾标题，避免无意义的 TMDB 查询."""

import re
from collections.abc import Callable

# 常见垃圾词黑名单（仅当标题完全由这些词组成时过滤）
_JUNK_WORDS = frozenset(
    [
        "www",
        "com",
        "net",
        "org",
        "tv",
        "download",
        "torrent",
        "magnet",
        "ddl",
        "free",
    ]
)

# 垃圾模式：纯网址类、无意义组合
_GARBAGE_PATTERNS = re.compile(
    r"^(?:www\s+\w+|\w+\s+(?:com|net|org|tv|cc|io)\b(?!\.?\w)|"
    r"\w+\s+\.(?:me)\b|"
    r"(?:pthdtv|qqhdtv|hdtv|hd|4k|1080p|720p)\s*$|"
    r"^\w{1,3}\s+(?:hd|tv|com)$)"
    r"|\b(?:pthdtv|qqhdtv)\b",
    re.IGNORECASE,
)


_TITLE_FILTERS: dict[str, list[Callable[[str], bool]]] = {}


def register_title_filter(filter_fn: Callable[[str], bool], plugin_id: str = "builtin") -> None:
    """注册插件级标题过滤器；返回 True 表示标题应被过滤。"""
    filters = _TITLE_FILTERS.setdefault(plugin_id, [])
    if filter_fn not in filters:
        filters.append(filter_fn)


def unregister_title_filters(plugin_id: str) -> None:
    _TITLE_FILTERS.pop(plugin_id, None)


def is_valid_media_title(name: str | None) -> bool:
    """
    校验解析后的媒体标题是否有效。

    规则：
    1. 不能为空
    2. 有效字符长度 >= 2
    3. 不能全部是垃圾词
    4. 通过插件注册的标题过滤器
    5. 不能是网址类垃圾组合

    :param name: 解析出的标题（en_name 或 cn_name）
    :return: 是否有效
    """
    if not name:
        return False
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]", "", name.lower().strip())
    if len(cleaned) < 2:
        return False
    if cleaned in _JUNK_WORDS:
        return False
    for filters in list(_TITLE_FILTERS.values()):
        for filter_fn in list(filters):
            try:
                if filter_fn(name):
                    return False
            except Exception:  # noqa: BLE001 - 单插件过滤器失败不影响主流程
                continue
    if _GARBAGE_PATTERNS.search(name):
        return False
    return True

"""季集字符串工具（无重依赖，供搜索结果与订阅共用）."""

from __future__ import annotations

import re

_EPISODE_PATTERNS = (
    r"(?i)\bS\d{1,2}\s*E(?:P)?\s*(\d{1,4})\b",
    r"(?i)(?:^|[\s._-])E(?:P|pisode)?\s*(\d{1,4})(?=\b|$)",
    r"(?:^|[\s._-])-\s*(\d{1,3})(?=\s|\b|$|\()",
    r"第\s*(\d{1,3})\s*[集话話]",
    r"[\[【(]\s*(\d{1,3})\s*[\]】)]",
)


def extract_episode_number(title: str) -> int | None:
    """从标题中提取单个集号；供搜索结果补全与季集键统一使用."""
    for pattern in _EPISODE_PATTERNS:
        match = re.search(pattern, str(title or ""))
        if not match:
            continue
        try:
            value = int(match.group(1))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


def infer_episode_key(se_key: str, title: str) -> str:
    """ES_STRING 只有季时，用标题中的常见集数写法补全，避免整季挤在一个表里."""
    if not se_key or se_key == "movie" or re.search(r"E\d", se_key, re.I):
        return se_key
    episode = extract_episode_number(title)
    if episode is None:
        return se_key
    season = se_key.split()[0]
    return f"{season} E{episode:02d}"

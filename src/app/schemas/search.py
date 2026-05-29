from dataclasses import dataclass
from typing import Any


@dataclass
class SearchOneMediaResultDTO:
    """单媒体搜索结果"""

    media_info: Any = None
    no_exists: dict | list | None = None
    total_count: int = 0
    download_count: int = 0


@dataclass
class SearchMediasResultDTO:
    """搜索返回结果列表"""

    results: list[Any] | None = None

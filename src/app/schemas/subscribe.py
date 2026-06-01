from dataclasses import dataclass
from typing import Any


@dataclass
class RssAddResultDTO:
    """RSS添加结果"""

    code: int = 0
    msg: str = ""
    rssid: Any = None
    media_info: Any = None


@dataclass
class RssDetailResultDTO:
    """RSS详情结果"""

    detail: dict | None = None
    mtype_str: str = ""


@dataclass
class RssHistoryResultDTO:
    """RSS历史记录结果"""

    items: list[dict] | None = None


@dataclass
class RssListResultDTO:
    """RSS列表结果"""

    movie_items: list[dict] | None = None
    tv_items: list[dict] | None = None
    movie_list: dict | None = None
    tv_list: dict | None = None


@dataclass
class RssIcalResultDTO:
    """RSS日历事件结果"""

    events: list[dict] | None = None

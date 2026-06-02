from dataclasses import dataclass
from typing import Any


@dataclass
class SubscribeAddResultDTO:
    """订阅添加结果"""

    code: int = 0
    msg: str = ""
    rssid: Any = None
    media_info: Any = None


@dataclass
class SubscribeDetailResultDTO:
    """订阅详情结果"""

    detail: dict | None = None
    mtype_str: str = ""


@dataclass
class SubscribeHistoryResultDTO:
    """订阅历史记录结果"""

    items: list[dict] | None = None


@dataclass
class SubscribeListResultDTO:
    """订阅列表结果"""

    movie_items: list[dict] | None = None
    tv_items: list[dict] | None = None
    movie_list: dict | None = None
    tv_list: dict | None = None


@dataclass
class SubscribeIcalResultDTO:
    """订阅日历事件结果"""

    events: list[dict] | None = None

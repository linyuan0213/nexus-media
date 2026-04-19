# -*- coding: utf-8 -*-
from dataclasses import dataclass
from typing import Any, List, Optional


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
    detail: Optional[dict] = None
    mtype_str: str = ""


@dataclass
class RssHistoryResultDTO:
    """RSS历史记录结果"""
    items: Optional[List[dict]] = None


@dataclass
class RssListResultDTO:
    """RSS列表结果"""
    movie_items: Optional[List[dict]] = None
    tv_items: Optional[List[dict]] = None
    movie_list: Optional[dict] = None
    tv_list: Optional[dict] = None


@dataclass
class RssIcalResultDTO:
    """RSS日历事件结果"""
    events: Optional[List[dict]] = None

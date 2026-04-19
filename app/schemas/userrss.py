# -*- coding: utf-8 -*-
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class UserRssArticleListDTO:
    articles: List[dict] = field(default_factory=list)
    count: int = 0
    uses: Optional[str] = None
    address_count: int = 0


@dataclass
class UserRssHistoryDTO:
    downloads: List[dict] = field(default_factory=list)
    count: int = 0


@dataclass
class UserRssArticleTestDTO:
    name: Optional[str] = None
    match_flag: Optional[bool] = None
    exist_flag: Optional[bool] = None
    media_dict: Optional[dict] = None


@dataclass
class UserRssTaskUpdateDTO:
    success: bool = False

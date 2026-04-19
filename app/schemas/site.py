# -*- coding: utf-8 -*-
from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class SiteAttrDTO:
    site_free: bool = False
    site_2xfree: bool = False
    site_hr: bool = False


@dataclass
class SiteDetailDTO:
    site: Any = None
    site_free: bool = False
    site_2xfree: bool = False
    site_hr: bool = False


@dataclass
class SiteTestResultDTO:
    flag: bool = False
    msg: str = ""
    times: float = 0.0
    code: int = 0


@dataclass
class SiteHistoryDTO:
    dataset: List[list] = field(default_factory=list)


@dataclass
class SiteSeedingDTO:
    dataset: List[list] = field(default_factory=list)


@dataclass
class SiteActivityDTO:
    dataset: List[list] = field(default_factory=list)


@dataclass
class SiteResourcesResultDTO:
    success: bool = False
    data: Any = None
    msg: str = ""


@dataclass
class SiteUpdateResultDTO:
    code: Optional[int] = None
    msg: Optional[str] = None

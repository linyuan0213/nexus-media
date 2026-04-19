# -*- coding: utf-8 -*-
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class DownloadResultDTO:
    """下载结果 DTO"""
    success: bool = False
    message: str = ""


@dataclass
class DownloadingTorrentDTO:
    """正在下载任务 DTO（含媒体信息组装后）"""
    id: str = ""
    name: str = ""
    title: str = ""
    image: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class IndexerStatisticsDTO:
    """索引器统计 DTO"""
    name: str = ""
    total: int = 0
    fail: int = 0
    success: int = 0
    avg: float = 0.0

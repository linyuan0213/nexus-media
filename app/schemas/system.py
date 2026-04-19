# -*- coding: utf-8 -*-
from dataclasses import dataclass


@dataclass
class BackupRestoreResultDTO:
    """备份恢复结果"""
    success: bool = False
    message: str = ""


@dataclass
class NetTestResultDTO:
    """网络测试结果"""
    success: bool = False
    time_ms: int = 0


@dataclass
class IndexerConfigResultDTO:
    """索引器配置保存结果"""
    success: bool = True
    code: int = 0
    msg: str = ""


@dataclass
class MediaServerConfigResultDTO:
    """媒体服务器配置保存结果"""
    success: bool = True
    code: int = 0
    msg: str = ""


@dataclass
class WebSearchResultDTO:
    """WEB搜索结果"""
    code: int = 0
    msg: str = ""


@dataclass
class VersionInfoDTO:
    """版本信息"""
    version: str = ""
    url: str = ""
    has_update: bool = False

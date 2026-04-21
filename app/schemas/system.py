# -*- coding: utf-8 -*-
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


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


@dataclass
class SendMessageResultDTO:
    """发送消息结果"""
    success: bool = False
    message: str = ""


@dataclass
class ProgressResultDTO:
    """进度查询结果"""
    value: int = 0
    text: str = ""
    exists: bool = False


@dataclass
class UserManageResultDTO:
    """用户管理结果"""
    success: bool = False
    message: str = ""


@dataclass
class ConfigUpdateResultDTO:
    """配置更新结果"""
    success: bool = False
    test_mode: bool = False

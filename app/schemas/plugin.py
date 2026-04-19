# -*- coding: utf-8 -*-
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class PluginAppsDTO:
    plugins: Any = None
    statistic: Any = None


@dataclass
class PluginPageDTO:
    title: Optional[str] = None
    content: Optional[str] = None
    func: Any = None


@dataclass
class PluginInstallResultDTO:
    success: bool = False
    msg: str = ""

# -*- coding: utf-8 -*-
from dataclasses import dataclass
from typing import Any, List, Optional


@dataclass
class BrushTaskDTO:
    task: Any = None


@dataclass
class BrushTorrentListDTO:
    torrents: Optional[List[dict]] = None

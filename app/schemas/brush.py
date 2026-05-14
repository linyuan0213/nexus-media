from dataclasses import dataclass
from typing import Any


@dataclass
class BrushTaskDTO:
    task: Any = None


@dataclass
class BrushTorrentListDTO:
    torrents: list[dict] | None = None

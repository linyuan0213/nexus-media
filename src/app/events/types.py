"""
事件类型定义
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Event:
    event_type: str
    payload: Any
    metadata: dict[str, Any] = field(default_factory=dict)

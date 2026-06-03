"""基础设施事件类型 — 纯数据，无应用层依赖."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Event:
    event_type: str
    payload: Any
    metadata: dict[str, Any] = field(default_factory=dict)

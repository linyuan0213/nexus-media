"""浏览器操作上下文与指标。

搜索、详情、userinfo 等入口使用同一套 trace/op 标识，便于串联日志和挑战指标；
指标只保存计数，不记录 URL/Cookie 等敏感数据。
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from time import monotonic
from typing import Any


@dataclass
class BrowserOperationContext:
    operation: str
    site_key: str
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    started_at: float = field(default_factory=monotonic)

    @classmethod
    def create(cls, operation: str, site_key: str) -> "BrowserOperationContext":
        return cls(operation=str(operation), site_key=str(site_key or ""))

    @property
    def op_id(self) -> str:
        return self.trace_id

    def fields(self, **extra: Any) -> str:
        data: dict[str, Any] = {
            "trace": self.trace_id,
            "op": self.operation,
            "site": self.site_key,
            "elapsed_ms": int((monotonic() - self.started_at) * 1000),
        }
        data.update(extra)
        return " ".join(f"{key}={value!r}" for key, value in data.items())


class BrowserOperationMetrics:
    """进程内挑战/失败计数；可被日志或后续 metrics exporter 读取。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._challenges: dict[str, dict[str, int]] = {}
        self._failures: dict[str, int] = {}

    def record_challenge(self, challenge_type: str, solved: bool = False) -> None:
        key = str(challenge_type or "unknown")
        with self._lock:
            item = self._challenges.setdefault(key, {"total": 0, "solved": 0})
            item["total"] += 1
            if solved:
                item["solved"] += 1

    def record_failure(self, operation: str) -> None:
        key = str(operation or "unknown")
        with self._lock:
            self._failures[key] = self._failures.get(key, 0) + 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "challenges": {key: dict(value) for key, value in self._challenges.items()},
                "failures": dict(self._failures),
            }


BROWSER_METRICS = BrowserOperationMetrics()

"""任务队列数据模型与状态定义."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.utils.json_utils import JsonUtils


class TaskStatus(str, Enum):
    """任务生命周期状态."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DEAD = "dead"

    @property
    def terminal(self) -> bool:
        return self in {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.DEAD}


class TaskQueueError(Exception):
    """任务队列基础异常."""


class QueueUnavailableError(TaskQueueError):
    """队列后端不可用（Redis 连接失败、AOF 未启用等）."""


@dataclass(slots=True)
class Task:
    """持久化任务。

    payload 必须是 JSON 可序列化对象；大文件请存路径或引用，不要直接塞进队列。
    """

    id: str
    queue_name: str
    task_type: str
    payload: dict[str, Any]
    dedup_key: str = ""
    priority: int = 0
    attempts: int = 0
    max_attempts: int = 5
    status: TaskStatus = TaskStatus.QUEUED
    stream_id: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    lease_owner: str = ""
    lease_until: float = 0.0
    last_error: str = ""
    result: dict[str, Any] | None = None

    @classmethod
    def create(
        cls,
        queue_name: str,
        task_type: str,
        payload: dict[str, Any],
        *,
        dedup_key: str = "",
        priority: int = 0,
        max_attempts: int = 5,
        task_id: str | None = None,
    ) -> Task:
        now = time.time()
        return cls(
            id=task_id or uuid.uuid4().hex,
            queue_name=queue_name,
            task_type=task_type,
            payload=payload,
            dedup_key=dedup_key,
            priority=int(priority),
            max_attempts=max(1, int(max_attempts)),
            created_at=now,
            updated_at=now,
        )

    def to_stream(self) -> dict[str, str]:
        """序列化为 Redis Stream 字段（全部为字符串）."""
        return {
            "task_id": self.id,
            "queue_name": self.queue_name,
            "task_type": self.task_type,
            "payload": JsonUtils.dumps(JsonUtils.to_jsonable(self.payload)),
            "dedup_key": self.dedup_key,
            "priority": str(self.priority),
            "attempts": str(self.attempts),
            "max_attempts": str(self.max_attempts),
            "created_at": f"{self.created_at:.6f}",
        }

    @classmethod
    def from_stream(cls, fields: dict[str, Any], stream_id: str = "") -> Task:
        """从 Redis Stream 字段还原任务（缺省字段保持安全默认值）."""
        payload: dict[str, Any] = {}
        raw_payload = fields.get("payload")
        if isinstance(raw_payload, (str, bytes)) and raw_payload:
            try:
                parsed = JsonUtils.loads(raw_payload)
            except Exception:
                parsed = None
            if isinstance(parsed, dict):
                payload = parsed
        return cls(
            id=_as_text(fields.get("task_id")),
            queue_name=_as_text(fields.get("queue_name")),
            task_type=_as_text(fields.get("task_type")),
            payload=payload,
            dedup_key=_as_text(fields.get("dedup_key")),
            priority=_as_int(fields.get("priority"), 0),
            attempts=_as_int(fields.get("attempts"), 0),
            max_attempts=max(1, _as_int(fields.get("max_attempts"), 5)),
            stream_id=stream_id,
            created_at=_as_float(fields.get("created_at"), time.time()),
        )

    def to_hash(self) -> dict[str, str]:
        """序列化为任务状态 hash，供查询/恢复使用."""
        data = self.to_stream()
        data.update(
            {
                "status": self.status.value,
                "stream_id": self.stream_id,
                "updated_at": f"{self.updated_at:.6f}",
                "lease_owner": self.lease_owner,
                "lease_until": f"{self.lease_until:.6f}",
                "last_error": self.last_error,
                "result": JsonUtils.dumps(JsonUtils.to_jsonable(self.result)) if self.result is not None else "",
            }
        )
        return data

    @classmethod
    def from_hash(cls, fields: dict[str, Any]) -> Task:
        """从状态 hash 还原任务."""
        task = cls.from_stream(fields, stream_id=str(fields.get("stream_id") or ""))
        task.status = _as_status(fields.get("status"))
        task.updated_at = _as_float(fields.get("updated_at"), task.created_at)
        task.lease_owner = str(fields.get("lease_owner") or "")
        task.lease_until = _as_float(fields.get("lease_until"), 0.0)
        task.last_error = str(fields.get("last_error") or "")
        raw_result = fields.get("result")
        if isinstance(raw_result, str) and raw_result:
            parsed = JsonUtils.loads(raw_result)
            if isinstance(parsed, dict):
                task.result = parsed
        return task


def _as_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value) if value is not None else ""


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_status(value: Any) -> TaskStatus:
    try:
        return TaskStatus(_as_text(value))
    except ValueError:
        return TaskStatus.QUEUED

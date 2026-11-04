"""Redis Streams 持久任务队列."""

from __future__ import annotations

import time
from typing import Any

from redis import StrictRedis
from redis.exceptions import RedisError, ResponseError

import log
from app.infrastructure.task_queue.base import TaskQueue
from app.infrastructure.task_queue.models import QueueUnavailableError, Task, TaskStatus


class RedisStreamTaskQueue(TaskQueue):
    """基于 Redis Stream consumer group 的持久任务队列.

    - Stream 保存任务字段，任务 hash 保存状态
    - XREADGROUP 领取，XACK+XDEL 完成，XAUTOCLAIM 回收崩溃/stale pending
    - 失败任务保留 pending，按 retry_idle_ms 重新投递
    - durable=True，但前提是 Redis 启用 AOF
    """

    def __init__(
        self,
        queue_name: str,
        *,
        host: str,
        port: int = 6379,
        password: str = "",
        db: int = 0,
        key_prefix: str = "nexus:task",
        require_aof: bool = False,
        lease_seconds: int = 120,
        retry_idle_ms: int = 30000,
        max_attempts: int = 5,
        dedup_ttl_seconds: int = 86400,
        task_ttl_seconds: int = 86400,
        client: Any | None = None,
    ):
        super().__init__(
            queue_name,
            lease_seconds=lease_seconds,
            max_attempts=max_attempts,
            dedup_ttl_seconds=dedup_ttl_seconds,
        )
        self._key_prefix = key_prefix.rstrip(":")
        self._stream = f"{self._key_prefix}:{queue_name}:stream"
        self._group = f"{self._key_prefix}:{queue_name}:workers"
        self._dead_stream = f"{self._key_prefix}:{queue_name}:dead"
        self._require_aof = require_aof
        self._aof_enabled = False
        self._retry_idle_ms = max(1, int(retry_idle_ms))
        self._task_ttl_seconds = max(0, int(task_ttl_seconds))
        self._client: Any = client or StrictRedis(
            host=host,
            port=port,
            password=password or None,
            db=db,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=10,
        )
        self._ensure_ready()

    @property
    def durable(self) -> bool:
        return self._aof_enabled

    def enqueue(
        self,
        task_type: str,
        payload: dict[str, Any],
        *,
        dedup_key: str = "",
        priority: int | None = None,
        max_attempts: int | None = None,
        task_id: str | None = None,
    ) -> Task:
        task = Task.create(
            self.queue_name,
            task_type,
            payload,
            dedup_key=dedup_key,
            priority=self.priority if priority is None else priority,
            max_attempts=self.max_attempts if max_attempts is None else max_attempts,
            task_id=task_id,
        )
        reserved = False
        try:
            if dedup_key:
                existing = self._reserve_dedup(dedup_key, task.id)
                if existing is not None:
                    return existing
                reserved = True
            self._client.xadd(self._stream, task.to_stream())
        except RedisError as exc:
            if reserved:
                self._release_dedup(dedup_key, task.id)
            raise QueueUnavailableError(f"Redis 入队失败: {exc}") from exc
        try:
            self._client.hset(self._task_key(task.id), mapping=task.to_hash())
        except RedisError as exc:
            # Stream 已写入，任务不会丢；hash 缺失时 worker 会从 stream 字段恢复
            log.warn(f"[TaskQueue]写初始任务状态失败 {task.id}: {exc}")
        return task

    def claim(self, consumer: str, *, count: int = 1, block_ms: int = 1000) -> list[Task]:
        messages: list[tuple[Any, dict[str, Any]]] = []
        messages.extend(self._reclaim_stale(consumer, count))
        remaining = max(0, max(1, count) - len(messages))
        if remaining:
            messages.extend(self._read_new(consumer, remaining, block_ms))

        claimed: list[Task] = []
        seen: set[str] = set()
        for stream_id, fields in messages:
            task_id = str(fields.get("task_id") or "")
            if not task_id or task_id in seen:
                continue
            seen.add(task_id)
            task = self._hydrate(task_id, fields, str(stream_id))
            if task is None:
                self._finish_stream_entry(str(stream_id))
                continue
            if task.status.terminal:
                self._finish_stream_entry(str(stream_id))
                continue
            now = time.time()
            task.status = TaskStatus.RUNNING
            task.stream_id = str(stream_id)
            task.lease_owner = consumer
            task.lease_until = now + self.lease_seconds
            task.updated_at = now
            self._write_hash(task)
            claimed.append(task)
            if len(claimed) >= max(1, count):
                break
        return claimed

    def heartbeat(self, task: Task) -> bool:
        if not task.stream_id:
            return False
        now = time.time()
        task.lease_until = now + self.lease_seconds
        task.updated_at = now
        self._write_hash(task)
        try:
            self._client.xclaim(
                self._stream,
                self._group,
                task.lease_owner,
                0,
                [task.stream_id],
                justid=True,
            )
            return True
        except RedisError:
            return False

    def ack(self, task: Task, result: dict[str, Any] | None = None) -> bool:
        task.status = TaskStatus.SUCCEEDED
        task.result = result
        task.lease_owner = ""
        task.lease_until = 0.0
        task.updated_at = time.time()
        try:
            if task.stream_id:
                self._client.xack(self._stream, self._group, task.stream_id)
                self._client.xdel(self._stream, task.stream_id)
            self._write_hash(task)
            self._expire_hash(task.id)
            return True
        except RedisError as exc:
            log.warn(f"[TaskQueue]ACK 失败 {task.id}: {exc}")
            return False

    def fail(self, task: Task, error: str, *, retryable: bool = True) -> bool:
        task.attempts = max(task.attempts, self._hash_attempts(task.id)) + 1
        task.last_error = error
        task.updated_at = time.time()
        try:
            if retryable and task.attempts < task.max_attempts:
                task.status = TaskStatus.QUEUED
                task.lease_owner = ""
                task.lease_until = 0.0
                self._write_hash(task)
                # 不 ACK，保留 pending，由 XAUTOCLAIM 在 retry_idle_ms 后重投
                return True
            task.status = TaskStatus.DEAD if retryable else TaskStatus.FAILED
            self._write_hash(task)
            self._client.xadd(self._dead_stream, task.to_stream() | {"last_error": error})
            if task.stream_id:
                self._client.xack(self._stream, self._group, task.stream_id)
                self._client.xdel(self._stream, task.stream_id)
            self._expire_hash(task.id)
            return True
        except RedisError as exc:
            log.warn(f"[TaskQueue]FAIL 失败 {task.id}: {exc}")
            return False

    def cancel(self, task: Task) -> bool:
        task.status = TaskStatus.CANCELLED
        task.lease_owner = ""
        task.lease_until = 0.0
        task.updated_at = time.time()
        try:
            if task.stream_id:
                self._client.xack(self._stream, self._group, task.stream_id)
                self._client.xdel(self._stream, task.stream_id)
            self._write_hash(task)
            self._expire_hash(task.id)
            return True
        except RedisError:
            return False

    def get(self, task_id: str) -> Task | None:
        try:
            fields = self._client.hgetall(self._task_key(task_id))
        except RedisError:
            return None
        if not fields:
            return None
        return Task.from_hash(fields)

    def pending(self) -> int:
        try:
            return int(self._client.xlen(self._stream))
        except RedisError:
            return 0

    def close(self) -> None:
        try:
            self._client.close()
        except Exception as exc:  # noqa: BLE001
            log.debug(f"[TaskQueue]关闭 Redis 连接失败: {exc}")

    def _ensure_ready(self) -> None:
        try:
            if not self._client.ping():
                raise QueueUnavailableError("Redis ping 失败")
            self._check_durability()
            try:
                self._client.xgroup_create(self._stream, self._group, id="0", mkstream=True)
            except ResponseError as exc:
                if "BUSYGROUP" not in str(exc):
                    raise
        except RedisError as exc:
            raise QueueUnavailableError(f"Redis 任务队列不可用: {exc}") from exc

    def _check_durability(self) -> None:
        try:
            info = self._client.info("persistence")
            aof = bool(info.get("aof_enabled"))
        except (RedisError, AttributeError):
            aof = False
        self._aof_enabled = aof
        if self._require_aof and not aof:
            raise QueueUnavailableError("Redis AOF 未启用，拒绝作为持久队列")
        if not aof:
            log.warn("[TaskQueue]Redis AOF 未启用，队列不具备强持久性")

    def _reserve_dedup(self, dedup_key: str, task_id: str) -> Task | None:
        key = self._dedup_key(dedup_key)
        kwargs = {"ex": self.dedup_ttl_seconds} if self.dedup_ttl_seconds else {}
        for _ in range(5):
            if self._client.set(key, task_id, nx=True, **kwargs):
                return None
            existing_id = self._client.get(key)
            if not existing_id:
                continue
            existing = self.get(str(existing_id))
            if existing is not None:
                return existing
            # 占位存在但任务 hash 尚未写入：删除后重新竞争，不能无占位直接入队。
            self._client.delete(key)
        raise QueueUnavailableError("dedup key 初始化竞争，拒绝无去重入队")

    def _release_dedup(self, dedup_key: str, task_id: str) -> None:
        if not dedup_key:
            return
        key = self._dedup_key(dedup_key)
        try:
            if str(self._client.get(key) or "") == task_id:
                self._client.delete(key)
        except RedisError:
            pass

    def _reclaim_stale(self, consumer: str, count: int) -> list[tuple[Any, dict[str, Any]]]:
        try:
            result = self._client.xautoclaim(
                self._stream,
                self._group,
                consumer,
                self._retry_idle_ms,
                start_id="0-0",
                count=max(1, count),
            )
            if isinstance(result, (list, tuple)) and len(result) >= 2:
                messages = result[1]
                return list(messages) if isinstance(messages, list) else []
            return []
        except (AttributeError, ResponseError):
            return self._reclaim_fallback(consumer, count)
        except RedisError as exc:
            raise QueueUnavailableError(f"Redis 回收 pending 失败: {exc}") from exc

    def _reclaim_fallback(self, consumer: str, count: int) -> list[tuple[Any, dict[str, Any]]]:
        try:
            pending = self._client.xpending_range(
                self._stream,
                self._group,
                min="-",
                max="+",
                count=max(1, count),
                idle=self._retry_idle_ms,
            )
            ids = [item.get("message_id") for item in pending if item.get("message_id")]
            if not ids:
                return []
            claimed = self._client.xclaim(
                self._stream,
                self._group,
                consumer,
                self._retry_idle_ms,
                ids,
            )
            return list(claimed) if isinstance(claimed, list) else []
        except RedisError:
            return []

    def _read_new(self, consumer: str, count: int, block_ms: int) -> list[tuple[Any, dict[str, Any]]]:
        try:
            result = self._client.xreadgroup(
                self._group,
                consumer,
                {self._stream: ">"},
                count=max(1, count),
                block=max(0, int(block_ms)),
            )
        except RedisError as exc:
            raise QueueUnavailableError(f"Redis 读取任务失败: {exc}") from exc
        messages: list[tuple[Any, dict[str, Any]]] = []
        if not isinstance(result, list):
            return messages
        for _stream, entries in result:
            if isinstance(entries, list):
                messages.extend(entries)
        return messages

    def _hydrate(self, task_id: str, fields: dict[str, Any], stream_id: str) -> Task | None:
        try:
            state = self._client.hgetall(self._task_key(task_id))
        except RedisError:
            state = {}
        try:
            task = Task.from_hash(state) if state else Task.from_stream(_decode_fields(fields), stream_id)
        except Exception:
            return None
        if not task.id:
            task.id = task_id
        task.stream_id = stream_id
        return task

    def _hash_attempts(self, task_id: str) -> int:
        try:
            raw = self._client.hget(self._task_key(task_id), "attempts")
            return int(raw) if raw is not None else 0
        except (RedisError, ValueError):
            return 0

    def _write_hash(self, task: Task) -> None:
        try:
            self._client.hset(self._task_key(task.id), mapping=task.to_hash())
        except RedisError as exc:
            log.warn(f"[TaskQueue]写任务状态失败 {task.id}: {exc}")

    def _expire_hash(self, task_id: str) -> None:
        if self._task_ttl_seconds <= 0:
            return
        try:
            self._client.expire(self._task_key(task_id), self._task_ttl_seconds)
        except RedisError:
            pass

    def _finish_stream_entry(self, stream_id: str) -> None:
        try:
            self._client.xack(self._stream, self._group, stream_id)
            self._client.xdel(self._stream, stream_id)
        except RedisError:
            pass

    def _task_key(self, task_id: str) -> str:
        return f"{self._key_prefix}:task:{task_id}"

    def _dedup_key(self, dedup_key: str) -> str:
        return f"{self._key_prefix}:{self.queue_name}:dedup:{dedup_key}"


def _decode_fields(fields: dict[Any, Any]) -> dict[str, Any]:
    return {str(k): v.decode("utf-8") if isinstance(v, bytes) else v for k, v in fields.items()}

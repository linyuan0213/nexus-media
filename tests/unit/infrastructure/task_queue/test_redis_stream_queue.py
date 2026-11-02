"""Redis Stream 后端测试（使用内存 fake，不依赖真实 Redis）."""

from __future__ import annotations

from typing import Any

from app.infrastructure.task_queue.models import TaskStatus
from app.infrastructure.task_queue.redis_stream import RedisStreamTaskQueue


class _FakeRedis:
    def __init__(self) -> None:
        self.info_value = {"aof_enabled": 1}
        self.streams: dict[str, list[tuple[str, dict[str, str]]]] = {}
        self.pending: dict[str, set[str]] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.strings: dict[str, str] = {}
        self.delivered: set[str] = set()
        self._seq = 0

    def ping(self) -> bool:
        return True

    def info(self, _section: str) -> dict[str, Any]:
        return self.info_value

    def xgroup_create(self, *_args, **_kwargs) -> bool:
        return True

    def set(self, key: str, value: str, nx: bool = False, ex: int | None = None) -> bool:
        del ex
        if nx and key in self.strings:
            return False
        self.strings[key] = value
        return True

    def get(self, key: str) -> str | None:
        return self.strings.get(key)

    def delete(self, *keys: str) -> int:
        for key in keys:
            self.strings.pop(key, None)
        return len(keys)

    def xadd(self, stream: str, fields: dict[str, str]) -> str:
        self._seq += 1
        stream_id = f"{self._seq}-0"
        self.streams.setdefault(stream, []).append((stream_id, dict(fields)))
        return stream_id

    def hset(
        self,
        name: str,
        mapping: dict[str, str] | None = None,
        key: str | None = None,
        value: str | None = None,
    ) -> int:
        target = self.hashes.setdefault(name, {})
        if mapping:
            target.update(mapping)
        elif key is not None and value is not None:
            target[key] = value
        return 1

    def hgetall(self, name: str) -> dict[str, str]:
        return dict(self.hashes.get(name, {}))

    def hget(self, name: str, key: str) -> str | None:
        return self.hashes.get(name, {}).get(key)

    def expire(self, _name: str, _seconds: int) -> bool:
        return True

    def xreadgroup(self, group: str, consumer: str, streams: dict[str, str], count: int, block: int):
        del consumer, block
        result = []
        for stream in streams:
            entries = []
            for stream_id, fields in self.streams.get(stream, []):
                if stream_id in self.delivered:
                    continue
                self.delivered.add(stream_id)
                self.pending.setdefault(stream_id, set()).add(group)
                entries.append((stream_id, dict(fields)))
                if len(entries) >= count:
                    break
            if entries:
                result.append((stream, entries))
        return result

    def xautoclaim(self, *_args, **_kwargs):
        return ["0-0", []]

    def xclaim(self, *_args, **_kwargs):
        return []

    def xpending_range(self, *_args, **_kwargs):
        return []

    def xack(self, stream: str, group: str, *ids: str) -> int:
        del stream
        for stream_id in ids:
            self.pending.setdefault(stream_id, set()).discard(group)
        return len(ids)

    def xdel(self, stream: str, *ids: str) -> int:
        keep = [(sid, fields) for sid, fields in self.streams.get(stream, []) if sid not in ids]
        self.streams[stream] = keep
        for stream_id in ids:
            self.pending.pop(stream_id, None)
        return len(ids)

    def xlen(self, stream: str) -> int:
        return len(self.streams.get(stream, []))

    def close(self) -> None:
        pass


def _queue(fake: _FakeRedis) -> RedisStreamTaskQueue:
    return RedisStreamTaskQueue(
        "demo",
        host="unused",
        key_prefix="test:task",
        dedup_ttl_seconds=60,
        client=fake,
    )


def test_redis_enqueue_claim_ack():
    fake = _FakeRedis()
    queue = _queue(fake)
    task = queue.enqueue("demo", {"value": 1}, dedup_key="same")
    duplicate = queue.enqueue("demo", {"value": 2}, dedup_key="same")
    assert duplicate.id == task.id
    assert queue.pending() == 1

    claimed = queue.claim("worker", count=1, block_ms=10)
    assert len(claimed) == 1
    assert claimed[0].id == task.id
    assert claimed[0].stream_id
    stored = queue.get(task.id)
    assert stored is not None
    assert stored.status is TaskStatus.RUNNING
    assert queue.ack(claimed[0], {"ok": True})
    stored = queue.get(task.id)
    assert stored is not None
    assert stored.status is TaskStatus.SUCCEEDED
    assert queue.pending() == 0


def test_redis_fail_keeps_retryable_task_queued():
    fake = _FakeRedis()
    queue = _queue(fake)
    task = queue.enqueue("demo", {}, max_attempts=2)
    claimed = queue.claim("worker", block_ms=10)[0]
    assert queue.fail(claimed, "boom")
    status = queue.get(task.id)
    assert status is not None
    assert status.status is TaskStatus.QUEUED
    assert status.attempts == 1


def test_redis_fail_exhausted_goes_dead():
    fake = _FakeRedis()
    queue = _queue(fake)
    task = queue.enqueue("demo", {}, max_attempts=1)
    claimed = queue.claim("worker", block_ms=10)[0]
    assert queue.fail(claimed, "boom")
    status = queue.get(task.id)
    assert status is not None
    assert status.status is TaskStatus.DEAD
    assert queue.pending() == 0

"""内存任务队列测试."""

from app.infrastructure.task_queue.memory_queue import MemoryTaskQueue
from app.infrastructure.task_queue.models import TaskStatus


def test_enqueue_claim_ack_and_dedup():
    queue = MemoryTaskQueue("demo", dedup_ttl_seconds=60)
    first = queue.enqueue("demo", {"value": 1}, dedup_key="same")
    duplicate = queue.enqueue("demo", {"value": 2}, dedup_key="same")
    assert duplicate.id == first.id
    assert queue.pending() == 1

    claimed = queue.claim("worker-1", count=1, block_ms=10)
    assert len(claimed) == 1
    assert claimed[0].id == first.id
    assert claimed[0].status is TaskStatus.RUNNING
    assert queue.ack(claimed[0], {"ok": True})
    stored = queue.get(first.id)
    assert stored is not None
    assert stored.status is TaskStatus.SUCCEEDED
    assert stored.result == {"ok": True}


def test_fail_retries_until_dead():
    queue = MemoryTaskQueue("demo", max_attempts=2)
    task = queue.enqueue("demo", {})
    claimed = queue.claim("worker", block_ms=10)[0]
    assert queue.fail(claimed, "boom")
    stored = queue.get(task.id)
    assert stored is not None
    assert stored.status is TaskStatus.QUEUED
    retried = queue.claim("worker", block_ms=10)[0]
    assert queue.fail(retried, "boom again")
    stored = queue.get(task.id)
    assert stored is not None
    assert stored.status is TaskStatus.DEAD


def test_non_retryable_failure_marks_failed():
    queue = MemoryTaskQueue("demo")
    task = queue.enqueue("demo", {})
    claimed = queue.claim("worker", block_ms=10)[0]
    assert queue.fail(claimed, "bad task", retryable=False)
    stored = queue.get(task.id)
    assert stored is not None
    assert stored.status is TaskStatus.FAILED

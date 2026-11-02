"""任务模型序列化测试."""

from app.infrastructure.task_queue.models import Task, TaskStatus


def test_task_round_trip_stream_and_hash():
    task = Task.create("download", "demo", {"url": "magnet:?xt=urn:btih:abc"}, dedup_key="abc", max_attempts=3)
    stream_task = Task.from_stream(task.to_stream(), stream_id="1-0")
    assert stream_task.id == task.id
    assert stream_task.payload == task.payload
    assert stream_task.stream_id == "1-0"

    task.status = TaskStatus.SUCCEEDED
    task.result = {"download_id": "42"}
    hash_task = Task.from_hash(task.to_hash())
    assert hash_task.status is TaskStatus.SUCCEEDED
    assert hash_task.result == {"download_id": "42"}
    assert hash_task.max_attempts == 3


def test_terminal_statuses():
    assert TaskStatus.SUCCEEDED.terminal
    assert TaskStatus.FAILED.terminal
    assert TaskStatus.CANCELLED.terminal
    assert TaskStatus.DEAD.terminal
    assert not TaskStatus.QUEUED.terminal
    assert not TaskStatus.RUNNING.terminal

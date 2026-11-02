"""任务队列后端选择测试."""

import pytest

from app.core.settings import QueueConfig, RedisConfig
from app.infrastructure.task_queue.factory import create_task_queue
from app.infrastructure.task_queue.memory_queue import MemoryTaskQueue
from app.infrastructure.task_queue.models import QueueUnavailableError
from app.infrastructure.task_queue.redis_stream import RedisStreamTaskQueue


class _FakeRedis:
    def __init__(self, aof: int = 1):
        self.info_value = {"aof_enabled": aof}

    def ping(self):
        return True

    def info(self, _section):
        return self.info_value

    def xgroup_create(self, *_args, **_kwargs):
        return True


def test_auto_uses_memory_when_redis_disabled():
    queue = create_task_queue(
        "demo",
        config=QueueConfig(backend="auto"),
        redis_config=RedisConfig(enabled=False),
    )
    assert isinstance(queue, MemoryTaskQueue)
    assert not queue.durable


def test_redis_backend_uses_injected_client():
    queue = create_task_queue(
        "demo",
        config=QueueConfig(backend="redis"),
        redis_config=RedisConfig(),
        redis_client=_FakeRedis(),
    )
    assert isinstance(queue, RedisStreamTaskQueue)
    assert queue.durable


def test_enabled_redis_with_require_aof_rejects_non_persistent_instance():
    with pytest.raises(QueueUnavailableError):
        create_task_queue(
            "demo",
            config=QueueConfig(backend="auto", require_aof=True),
            redis_config=RedisConfig(),
            redis_client=_FakeRedis(aof=0),
        )

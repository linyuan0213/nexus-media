"""通用持久任务队列基础设施."""

from app.infrastructure.task_queue.base import TaskQueue
from app.infrastructure.task_queue.factory import create_task_queue
from app.infrastructure.task_queue.memory_queue import MemoryTaskQueue
from app.infrastructure.task_queue.models import (
    QueueUnavailableError,
    Task,
    TaskQueueError,
    TaskStatus,
)
from app.infrastructure.task_queue.redis_stream import RedisStreamTaskQueue
from app.infrastructure.task_queue.worker import TaskHandler, TaskWorker

__all__ = [
    "MemoryTaskQueue",
    "QueueUnavailableError",
    "RedisStreamTaskQueue",
    "Task",
    "TaskHandler",
    "TaskQueue",
    "TaskQueueError",
    "TaskStatus",
    "TaskWorker",
    "create_task_queue",
]

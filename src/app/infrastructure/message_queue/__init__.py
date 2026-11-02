"""
队列基础设施
提供内存队列和 Redis Stream 两种实现，统一接口
"""

from app.infrastructure.queue.base import MessageQueue
from app.infrastructure.queue.factory import MessageQueueFactory
from app.infrastructure.queue.memory_queue import MemoryMessageQueue
from app.infrastructure.queue.redis_queue import RedisMessageQueue

__all__ = [
    "MessageQueue",
    "MemoryMessageQueue",
    "RedisMessageQueue",
    "MessageQueueFactory",
]

"""
消息队列基础设施
提供内存队列和 Redis Stream 两种实现，统一接口
"""

from app.infrastructure.message_queue.base import MessageQueue
from app.infrastructure.message_queue.factory import MessageQueueFactory
from app.infrastructure.message_queue.memory_queue import MemoryMessageQueue
from app.infrastructure.message_queue.redis_queue import RedisMessageQueue

__all__ = [
    "MessageQueue",
    "MemoryMessageQueue",
    "RedisMessageQueue",
    "MessageQueueFactory",
]

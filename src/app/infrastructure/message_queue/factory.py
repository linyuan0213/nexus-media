"""
消息队列工厂 — 根据 Redis 可用性自动选择实现
"""

import threading

import log
from app.infrastructure.queue.base import MessageQueue
from app.infrastructure.queue.memory_queue import MemoryMessageQueue
from app.infrastructure.queue.redis_queue import RedisMessageQueue


class MessageQueueFactory:
    """消息队列工厂（线程安全单例）"""

    _instance: MessageQueue | None = None
    _lock = threading.Lock()

    @classmethod
    def create(cls, max_workers: int = 5) -> MessageQueue:
        """
        创建消息队列实例（单例）
        Redis 可用时返回 RedisMessageQueue，否则返回 MemoryMessageQueue
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    redis_queue = RedisMessageQueue(max_workers=max_workers)
                    if redis_queue.is_available():
                        cls._instance = redis_queue
                        log.info("[MessageQueueFactory]使用 Redis Stream 消息队列")
                    else:
                        mem_queue = MemoryMessageQueue(max_workers=max_workers)
                        mem_queue.start()
                        cls._instance = mem_queue
                        log.info("[MessageQueueFactory]使用内存消息队列（Redis 不可用）")
        elif isinstance(cls._instance, RedisMessageQueue) and not cls._instance.is_available():
            with cls._lock:
                if isinstance(cls._instance, RedisMessageQueue) and not cls._instance.is_available():
                    log.warn("[MessageQueueFactory]Redis 队列已不可用，降级到内存队列")
                    cls._instance.stop(wait=False)
                    mem_queue = MemoryMessageQueue(max_workers=max_workers)
                    mem_queue.start()
                    cls._instance = mem_queue
        return cls._instance

"""
消息队列工厂 — 根据 Redis 可用性自动选择实现
"""

import log
from app.infrastructure.queue.base import MessageQueue
from app.infrastructure.queue.memory_queue import MemoryMessageQueue
from app.infrastructure.queue.redis_queue import RedisMessageQueue


class MessageQueueFactory:
    """消息队列工厂"""

    _instance: MessageQueue = None

    @classmethod
    def create(cls, max_workers: int = 5) -> MessageQueue:
        """
        创建消息队列实例
        Redis 可用时返回 RedisMessageQueue，否则返回 MemoryMessageQueue
        """
        if cls._instance is not None:
            # 如果缓存的是 Redis 队列但当前不可用，降级到内存队列
            if isinstance(cls._instance, RedisMessageQueue) and not cls._instance.is_available():
                log.warn("【MessageQueueFactory】Redis 队列已不可用，降级到内存队列")
                cls._instance.stop(wait=False)
                cls._instance = None
            else:
                return cls._instance

        # 尝试 Redis
        redis_queue = RedisMessageQueue(max_workers=max_workers)
        if redis_queue.is_available():
            cls._instance = redis_queue
            log.info("【MessageQueueFactory】使用 Redis Stream 消息队列")
            return cls._instance

        # 降级到内存队列
        mem_queue = MemoryMessageQueue(max_workers=max_workers)
        mem_queue.start()
        cls._instance = mem_queue
        log.info("【MessageQueueFactory】使用内存消息队列（Redis 不可用）")
        return cls._instance

    @classmethod
    def get_instance(cls) -> MessageQueue:
        """获取当前队列实例"""
        if cls._instance is None:
            return cls.create()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """重置工厂（主要用于测试）"""
        if cls._instance:
            cls._instance.stop()
            cls._instance = None

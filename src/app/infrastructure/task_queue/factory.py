"""任务队列后端选择."""

from __future__ import annotations

from typing import Any

import log
from app.core.settings import QueueConfig, RedisConfig, settings
from app.infrastructure.task_queue.base import TaskQueue
from app.infrastructure.task_queue.memory_queue import MemoryTaskQueue
from app.infrastructure.task_queue.redis_stream import RedisStreamTaskQueue


def create_task_queue(
    queue_name: str,
    *,
    config: QueueConfig | None = None,
    redis_config: RedisConfig | None = None,
    redis_client: Any | None = None,
) -> TaskQueue:
    """按配置创建队列。

    auto: Redis 启用时使用 Redis；Redis 明确禁用时使用内存。
    Redis 已启用但连接失败/AOF 不满足要求时直接抛错，不静默降级。
    """
    queue_config = config or settings.queue
    redis_config = redis_config or settings.redis
    backend = (queue_config.backend or "auto").strip().lower()

    if backend == "memory":
        return _memory_queue(queue_name, queue_config)
    if backend == "redis":
        return _redis_queue(queue_name, queue_config, redis_config, redis_client)
    if backend == "auto":
        if not getattr(redis_config, "enabled", True):
            log.warn("[TaskQueue]Redis 未启用，使用内存队列（重启丢失）")
            return _memory_queue(queue_name, queue_config)
        return _redis_queue(queue_name, queue_config, redis_config, redis_client)
    raise ValueError(f"不支持的队列后端: {queue_config.backend}")


def _memory_queue(queue_name: str, config: QueueConfig) -> MemoryTaskQueue:
    return MemoryTaskQueue(
        queue_name,
        maxsize=config.memory_maxsize,
        lease_seconds=config.lease_seconds,
        max_attempts=config.max_attempts,
        dedup_ttl_seconds=config.dedup_ttl_seconds,
    )


def _redis_queue(
    queue_name: str,
    config: QueueConfig,
    redis_config: RedisConfig,
    client: Any | None,
) -> RedisStreamTaskQueue:
    return RedisStreamTaskQueue(
        queue_name,
        host=redis_config.host,
        port=redis_config.port,
        password=redis_config.password,
        db=redis_config.db,
        key_prefix=config.key_prefix,
        require_aof=config.require_aof,
        lease_seconds=config.lease_seconds,
        retry_idle_ms=config.retry_idle_ms,
        max_attempts=config.max_attempts,
        dedup_ttl_seconds=config.dedup_ttl_seconds,
        task_ttl_seconds=config.task_ttl_seconds,
        client=client,
    )

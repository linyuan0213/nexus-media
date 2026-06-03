"""LockManager - 分布式锁管理器.

自动检测 Redis 可用性，优先使用 Redis 分布式锁，Redis 不可用时降级为数据库锁.
"""

from collections.abc import Callable

from app.infrastructure.distributed_lock.base import DistributedLock, LockAcquisitionError
from app.infrastructure.distributed_lock.db_lock import DbDistributedLock
from app.infrastructure.distributed_lock.redis_lock import RedisDistributedLock
from app.infrastructure.redis import RedisStore


class LockManager:
    """分布式锁管理器.

    职责：
    1. 自动检测 Redis 可用性，优先 Redis 锁
    2. Redis 不可用时降级为数据库锁
    3. 提供统一的锁创建接口
    """

    def __init__(self, redis_store: RedisStore | None = None):
        self._redis_store = redis_store or RedisStore()

    def create_lock(self, lock_key: str, ttl_seconds: int = 60) -> DistributedLock:
        """创建分布式锁实例.

        :param lock_key: 锁键名
        :param ttl_seconds: 锁超时时间（秒）
        :return: DistributedLock 实例
        """
        if self._redis_store.is_available():
            return RedisDistributedLock(lock_key, ttl_seconds, self._redis_store)
        return DbDistributedLock(lock_key, ttl_seconds)

    def is_redis_available(self) -> bool:
        """检查 Redis 是否可用."""
        return self._redis_store.is_available()


_lock_manager: LockManager | None = None


def get_lock_manager() -> LockManager:
    """获取全局 LockManager 实例."""
    global _lock_manager
    if _lock_manager is None:
        _lock_manager = LockManager()
    return _lock_manager


def with_distributed_lock(
    lock_key: str,
    ttl_seconds: int = 60,
    lock_manager: LockManager | None = None,
    skip_on_locked: bool = True,
):
    """装饰器：为函数添加分布式锁.

    :param lock_key: 锁键名，支持 {func_name} 占位符
    :param ttl_seconds: 锁超时时间（秒）
    :param lock_manager: LockManager 实例，默认使用全局实例
    :param skip_on_locked: 当锁被占用时是否静默跳过（不抛异常）
    """

    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            lm = lock_manager or get_lock_manager()
            key = lock_key.format(func_name=func.__name__)
            lock = lm.create_lock(key, ttl_seconds)

            acquired = lock.acquire()
            if not acquired:
                if skip_on_locked:
                    return None
                raise LockAcquisitionError(f"无法获取锁: {key}")

            try:
                return func(*args, **kwargs)
            finally:
                lock.release()

        return wrapper

    return decorator

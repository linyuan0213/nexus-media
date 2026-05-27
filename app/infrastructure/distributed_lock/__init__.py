"""distributed_lock package - 分布式锁实现."""

from app.infrastructure.distributed_lock.base import DistributedLock, LockAcquisitionError
from app.infrastructure.distributed_lock.db_lock import DbDistributedLock
from app.infrastructure.distributed_lock.lock_manager import LockManager, get_lock_manager, with_distributed_lock
from app.infrastructure.distributed_lock.redis_lock import RedisDistributedLock

__all__ = [
    "DistributedLock",
    "LockAcquisitionError",
    "RedisDistributedLock",
    "DbDistributedLock",
    "LockManager",
    "get_lock_manager",
    "with_distributed_lock",
]

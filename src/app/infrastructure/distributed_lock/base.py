"""DistributedLock - 分布式锁抽象基类与上下文管理器."""

import os
import uuid
from abc import ABC, abstractmethod


class DistributedLock(ABC):
    """分布式锁抽象基类.

    所有分布式锁实现必须继承此类并提供 acquire/release 方法.
    """

    def __init__(self, lock_key: str, ttl_seconds: int = 60):
        self._lock_key = lock_key
        self._ttl_seconds = ttl_seconds
        self._token = f"{os.environ.get('SERVER_INSTANCE', 'default')}:{uuid.uuid4().hex}"
        self._owned = False

    @property
    def lock_key(self) -> str:
        return self._lock_key

    @property
    def owned(self) -> bool:
        return self._owned

    @abstractmethod
    def acquire(self) -> bool:
        """尝试获取锁.

        :return: True 表示获取成功，False 表示获取失败（锁已被其他实例持有）
        """
        ...

    @abstractmethod
    def release(self) -> None:
        """释放锁. 只有持有当前 token 的实例才能释放."""
        ...

    @abstractmethod
    def extend(self, additional_seconds: int) -> bool:
        """延长锁的过期时间.

        :param additional_seconds: 要延长的秒数
        :return: True 表示延长成功
        """
        ...

    def __enter__(self):
        if self._owned:
            return self
        if not self.acquire():
            raise LockAcquisitionError(f"无法获取锁: {self._lock_key}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False


class LockAcquisitionError(Exception):
    """锁获取失败异常."""

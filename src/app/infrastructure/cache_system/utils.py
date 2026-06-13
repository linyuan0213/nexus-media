"""
缓存工具类
"""

import hashlib
import pickle
from collections.abc import Callable
from typing import Any

import log


class CacheKeyBuilder:
    """缓存键构建器"""

    @staticmethod
    def simple(*parts) -> str:
        """简单键构建"""
        return ":".join(str(p) for p in parts)

    @staticmethod
    def with_prefix(prefix: str, *parts) -> str:
        """带前缀的键构建"""
        return f"{prefix}:{':'.join(str(p) for p in parts)}"

    @staticmethod
    def from_func(func: Callable, *args, **kwargs) -> str:
        """从函数调用构建键"""
        key_parts = [func.__qualname__]
        key_parts.extend(str(arg) for arg in args)
        key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
        return ":".join(key_parts)

    @staticmethod
    def hash_key(*parts) -> str:
        """构建哈希键（用于长键）"""
        key_str = ":".join(str(p) for p in parts)
        return hashlib.md5(key_str.encode(), usedforsecurity=False).hexdigest()

    @staticmethod
    def typed(prefix: str, type_val: Any, *parts) -> str:
        """带类型的键构建"""
        type_str = type_val.value if hasattr(type_val, "value") else str(type_val)
        return f"{prefix}:{type_str}:{':'.join(str(p) for p in parts)}"


def serialize_value(value: Any) -> bytes:
    """序列化值"""
    return pickle.dumps(value)


def deserialize_value(data: bytes) -> Any:
    """反序列化值"""
    return pickle.loads(data)  # nosec B301


def safe_serialize(value: Any) -> bytes | None:
    """安全序列化（失败返回None）"""
    try:
        return pickle.dumps(value)
    except Exception as e:  # noqa: BLE001
        log.debug(f"[Cache]序列化失败: {e}")
        return None


def safe_deserialize(data: bytes) -> Any | None:
    """安全反序列化（失败返回None）"""
    try:
        return pickle.loads(data)  # nosec B301
    except Exception as e:  # noqa: BLE001
        log.debug(f"[Cache]反序列化失败: {e}")
        return None

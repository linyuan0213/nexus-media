"""
缓存事件系统

支持监听缓存变更事件，实现缓存数据的同步和通知
"""

import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import Any

import log


class CacheEventType(Enum):
    """缓存事件类型"""

    SET = auto()
    GET = auto()
    DELETE = auto()
    EXPIRE = auto()
    CLEAR = auto()
    HIT = auto()
    MISS = auto()
    EVICT = auto()


@dataclass
class CacheEvent:
    """缓存事件"""

    event_type: CacheEventType
    cache_name: str
    key: str | None = None
    value: Any = None
    ttl: int | None = None
    timestamp: datetime | None = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class CacheEventListener(ABC):
    """缓存事件监听器基类"""

    @abstractmethod
    def on_event(self, event: CacheEvent):
        pass

    def __call__(self, event: CacheEvent):
        self.on_event(event)


class CacheEventManager:
    """缓存事件管理器"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._listeners: dict[CacheEventType, list[tuple]] = {event_type: [] for event_type in CacheEventType}
        self._global_listeners: list[Callable] = []
        self._lock = threading.RLock()
        self._enabled = True
        self._initialized = True

        log.debug("[CacheEventManager]缓存事件管理器初始化完成")

    def add_listener(
        self,
        listener: Callable[[CacheEvent], None],
        event_types: set[CacheEventType] | None = None,
        cache_name_pattern: str = "*",
    ):
        with self._lock:
            if event_types is None:
                self._global_listeners.append(listener)
            else:
                for event_type in event_types:
                    self._listeners[event_type].append((cache_name_pattern, listener))

    def remove_listener(self, listener: Callable[[CacheEvent], None]):
        with self._lock:
            if listener in self._global_listeners:
                self._global_listeners.remove(listener)

            for event_type in CacheEventType:
                self._listeners[event_type] = [
                    (pattern, lst) for pattern, lst in self._listeners[event_type] if lst != listener
                ]

    def emit(self, event: CacheEvent):
        if not self._enabled:
            return

        import fnmatch

        with self._lock:
            for listener in self._global_listeners:
                try:
                    listener(event)
                except Exception as e:
                    log.error(f"[CacheEventManager]监听器执行失败: {e}")

            listeners = self._listeners.get(event.event_type, [])
            for pattern, listener in listeners:
                try:
                    if pattern == "*" or fnmatch.fnmatch(event.cache_name, pattern):
                        listener(event)
                except Exception as e:
                    log.error(f"[CacheEventManager]监听器执行失败: {e}")

    def enable(self):
        self._enabled = True

    def disable(self):
        self._enabled = False


def get_event_manager() -> CacheEventManager:
    return CacheEventManager()


def on_cache_event(event_types: set[CacheEventType] | None = None, cache_name_pattern: str = "*"):
    def decorator(func: Callable[[CacheEvent], None]):
        manager = get_event_manager()
        manager.add_listener(func, event_types, cache_name_pattern)
        return func

    return decorator

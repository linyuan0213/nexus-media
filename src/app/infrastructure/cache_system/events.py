"""缓存事件系统 — 与 EventBus 整合，支持监听缓存变更事件。

保留本地高性能监听器 + 可选 EventBus 桥接。
EventBus 通过 init_event_bridge() 注入，避免导入时触发 app.events 循环依赖。
"""

import fnmatch
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import Any

import log
from app.infrastructure.event import Event


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


class CacheEventManager:
    """缓存事件管理器 — 本地高性能分发 + EventBus 桥接"""

    def __init__(self, event_bus=None):
        self._listeners: dict[CacheEventType, list[tuple]] = {event_type: [] for event_type in CacheEventType}
        self._global_listeners: list[Callable] = []
        self._lock = threading.RLock()
        self._enabled = True
        self._event_bus = event_bus

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

        if self._event_bus:
            try:
                self._event_bus.publish(
                    Event(
                        event_type=f"cache.{event.event_type.name.lower()}",
                        payload=event,
                    )
                )
            except Exception as e:
                log.debug(f"[CacheEventManager]EventBus 桥接失败: {e}")

    def enable(self):
        self._enabled = True

    def disable(self):
        self._enabled = False


_instance: CacheEventManager | None = None
_lock = threading.Lock()


def get_event_manager() -> CacheEventManager:
    """获取缓存事件管理器实例."""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = CacheEventManager()
    return _instance


def init_event_bridge(event_bus) -> None:
    """注入 EventBus 桥接（从 application 启动时调用）."""
    get_event_manager()._event_bus = event_bus


def on_cache_event(event_types: set[CacheEventType] | None = None, cache_name_pattern: str = "*"):
    def decorator(func: Callable[[CacheEvent], None]):
        manager = get_event_manager()
        manager.add_listener(func, event_types, cache_name_pattern)
        return func

    return decorator

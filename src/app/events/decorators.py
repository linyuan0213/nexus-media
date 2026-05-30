"""事件装饰器 — 支持 @on_event 声明式注册."""

from collections import defaultdict
from collections.abc import Callable
from typing import Any

_pending_handlers: dict[str, list[Callable[[Any], None]]] = defaultdict(list)


def on_event(event_type: str) -> Callable:
    """将函数注册为指定事件类型的处理器."""

    def decorator(func: Callable[[Any], None]) -> Callable[[Any], None]:
        _pending_handlers[event_type].append(func)
        return func

    return decorator


def auto_register(event_bus: Any) -> None:
    """将所有 pending 的处理器注册到 EventBus 实例."""
    from app.events.bus import EventBus

    if not isinstance(event_bus, EventBus):
        return

    for event_type, handlers in _pending_handlers.items():
        for handler in handlers:
            event_bus.subscribe(event_type, handler)

    _pending_handlers.clear()


def get_subscribers() -> list[tuple[str, list[Callable[[Any], None]]]]:
    """获取当前所有 pending 的处理器（主要用于测试）."""
    return list(_pending_handlers.items())


def clear_subscribers() -> None:
    """清空所有 pending 的处理器（用于测试重置）."""
    _pending_handlers.clear()

"""事件装饰器 — 支持 @on_event 声明式注册."""

from collections import defaultdict
from collections.abc import Callable
from typing import Any

from app.di import container
from app.events.bus import EventBus

_pending_handlers: dict[str, list[Callable[[Any], None]]] = defaultdict(list)


def on_event(event_type: str) -> Callable:
    """将函数注册为指定事件类型的处理器.

    定义时直接注册到 EventBus；若 EventBus 尚未就绪则暂存到 pending，
    待 EventBus 创建后由 auto_register 统一注册。
    """

    def decorator(func: Callable[[Any], None]) -> Callable[[Any], None]:
        try:
            container.event_bus().subscribe(event_type, func)
        except Exception:
            _pending_handlers[event_type].append(func)
        return func

    return decorator


def auto_register(event_bus: Any) -> None:
    """将所有 pending 的处理器注册到 EventBus 实例.

    在 EventBus 工厂函数中调用，处理那些定义时 EventBus 尚未创建的处理器。
    """
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

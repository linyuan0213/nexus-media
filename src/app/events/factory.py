"""
EventBus 工厂函数
用于 DI 容器延迟创建 EventBus 实例
"""

from app.events.bus import EventBus
from app.events.decorators import auto_register
from app.events.middleware import ErrorHandlingMiddleware, LoggingMiddleware
from app.events.registry import EventHandlerRegistry
from app.infrastructure.queue.factory import MessageQueueFactory


_ASYNC_EVENT_TYPES = {
    "media.transfer_finished",
    "media.episode_transferred",
    "subscribe.finished",
    "message.incoming",
}


def create_event_bus() -> EventBus:
    """创建并配置 EventBus 实例（供 DI 容器使用）"""
    registry = EventHandlerRegistry()
    queue = MessageQueueFactory.create(max_workers=4)
    bus = EventBus(
        registry=registry,
        message_queue=queue,
        middleware=[
            LoggingMiddleware(),
            ErrorHandlingMiddleware(),
        ],
        async_event_types=_ASYNC_EVENT_TYPES,
    )
    auto_register(bus)
    return bus

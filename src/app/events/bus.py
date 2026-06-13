"""
事件总线
复用 app.infrastructure.queue 作为异步投递后端
"""

from app.events.bridge import PluginBridge
from app.events.middleware import Middleware, MiddlewareChain
from app.events.registry import EventHandlerRegistry
from app.events.types import Event
from app.infrastructure.queue.base import MessageQueue


class EventBus:
    """
    统一事件总线
    - 同步执行：关键事件（如转移完成后的后续操作）
    - 异步队列：非关键事件（如通知、日志），通过 MessageQueue 投递
    - 所有事件都会转发到 PluginBridge（HookSystem）

    由 lifespan 通过 AppContext 创建并管理生命周期。
    """

    def __init__(
        self,
        registry: EventHandlerRegistry,
        bridge: PluginBridge,
        message_queue: MessageQueue | None = None,
        middleware: list[Middleware] | None = None,
        async_event_types: set[str] | None = None,
    ):
        self._registry = registry
        self._queue = message_queue
        self._middleware = middleware or []
        self._async_types = async_event_types or set()
        self._bridge = bridge

    def shutdown(self) -> None:
        """关闭事件总线，停止所有异步任务"""
        if self._queue:
            self._queue.stop()

    def publish(self, event: Event) -> None:
        handlers = self._registry.get_handlers(event.event_type)
        is_async = event.event_type in self._async_types

        def _execute():
            # 1. 执行本地 handlers
            if handlers:

                def _run_handlers(e: Event) -> None:
                    for h in handlers:
                        h(e)

                chain = MiddlewareChain(self._middleware, _run_handlers)
                chain.execute(event)
            # 2. 转发到插件（始终执行）
            self._bridge.forward(event)

        if is_async and self._queue:
            self._queue.submit(_execute, name=f"event:{event.event_type}")
        else:
            _execute()

    def subscribe(self, event_type: str, handler, priority: int = 100) -> None:
        self._registry.subscribe(event_type, handler, priority)

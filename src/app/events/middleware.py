"""
事件中间件
"""

from abc import ABC, abstractmethod
from collections.abc import Callable

import log

from app.events.types import Event


class Middleware(ABC):
    """事件中间件基类"""

    @abstractmethod
    def process(self, event: Event, next_handler: Callable[[], None]) -> None:
        """处理事件，完成后调用 next_handler() 继续链"""


class LoggingMiddleware(Middleware):
    """日志中间件"""

    def process(self, event: Event, next_handler: Callable[[], None]) -> None:
        log.debug(f"[EventBus] 处理事件: {event.event_type}, payload={type(event.payload).__name__}")
        next_handler()


class ErrorHandlingMiddleware(Middleware):
    """错误处理中间件：单个 Handler 失败不影响其他 Handler"""

    def process(self, event: Event, next_handler: Callable[[], None]) -> None:
        try:
            next_handler()
        except Exception as e:
            log.error(f"[EventBus] 事件处理失败: {event.event_type} - {e}")


class MiddlewareChain:
    """显式 middleware 链，避免 lambda 闭包陷阱"""

    def __init__(self, middlewares: list[Middleware], final: Callable[[Event], None]):
        self._middlewares = middlewares
        self._final = final

    def execute(self, event: Event) -> None:
        self._invoke(0, event)

    def _invoke(self, index: int, event: Event) -> None:
        if index >= len(self._middlewares):
            self._final(event)
            return
        self._middlewares[index].process(event, lambda: self._invoke(index + 1, event))

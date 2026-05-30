"""
事件系统公共接口
"""

from app.events.bus import EventBus
from app.events.decorators import auto_register, clear_subscribers, on_event
from app.events.middleware import ErrorHandlingMiddleware, LoggingMiddleware, Middleware, MiddlewareChain
from app.events.registry import EventHandlerRegistry
from app.events.types import Event

__all__ = [
    "Event",
    "EventBus",
    "EventHandlerRegistry",
    "Middleware",
    "MiddlewareChain",
    "LoggingMiddleware",
    "ErrorHandlingMiddleware",
    "on_event",
    "auto_register",
    "clear_subscribers",
]

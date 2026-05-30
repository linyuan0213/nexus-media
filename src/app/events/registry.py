"""
事件处理器注册表
按 event_type + priority 分组管理 handlers
"""

from collections import defaultdict
from collections.abc import Callable

from app.events.types import Event


class EventHandlerRegistry:
    """事件处理器注册表"""

    def __init__(self):
        self._handlers: dict[str, list[tuple[int, Callable[[Event], None]]]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: Callable[[Event], None], priority: int = 100) -> None:
        """订阅事件，priority 越小越先执行"""
        handlers = self._handlers[event_type]
        handlers.append((priority, handler))
        handlers.sort(key=lambda x: x[0])

    def get_handlers(self, event_type: str) -> list[Callable[[Event], None]]:
        """获取指定事件类型的所有 handlers（已按 priority 排序）"""
        return [h for _, h in self._handlers.get(event_type, [])]

    def unsubscribe(self, event_type: str, handler: Callable[[Event], None]) -> None:
        """取消订阅"""
        handlers = self._handlers.get(event_type, [])
        self._handlers[event_type] = [(p, h) for p, h in handlers if h != handler]

    def clear(self) -> None:
        """清空所有注册"""
        self._handlers.clear()

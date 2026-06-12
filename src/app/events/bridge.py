"""
插件事件桥接
将事件转发到 HookSystem，EventBus 内置调用，不通过 registry subscribe
"""

import log
from app.events.types import Event


class PluginBridge:
    """将事件桥接到 HookSystem"""

    def __init__(self, hook_system):
        self._hook_system = hook_system

    def forward(self, event: Event) -> None:
        payload = getattr(event.payload, "__dict__", event.payload) if event.payload else {}
        try:
            self._hook_system.emit(event.event_type, payload)
        except Exception as e:
            log.debug(f"[PluginBridge] HookSystem 转发失败 {event.event_type}: {e}")

"""
Hook System - 全局事件钩子系统
插件通过注册钩子来响应系统事件
"""

import log
from app.di import container


class HookSystem:
    """全局事件钩子系统——插件可自由注册任意事件，无白名单限制"""

    def __init__(self):
        self._repo = container.plugin_framework_repo()
        self._handlers: dict[str, list[dict]] = {}
        self._load_from_db()

    def _load_from_db(self):
        """从数据库加载钩子订阅"""
        try:
            records = self._repo.get_all_hooks()
            for r in records:
                event = getattr(r, "EVENT", None)
                plugin_id = getattr(r, "PLUGIN_ID", None)
                if event and plugin_id:
                    self._handlers.setdefault(event, [])
                    if plugin_id not in [h["plugin_id"] for h in self._handlers[event]]:
                        self._handlers[event].append({"plugin_id": plugin_id})
        except Exception as e:
            log.warn(f"[HookSystem] 加载钩子订阅失败（可能表尚未创建）: {e}")

    def register(self, event: str, plugin_id: str) -> None:
        """注册钩子订阅——允许任意事件名"""
        self._handlers.setdefault(event, [])
        if plugin_id not in [h["plugin_id"] for h in self._handlers[event]]:
            self._handlers[event].append({"plugin_id": plugin_id})
            try:
                self._repo.insert_hook(plugin_id, event)
            except Exception as e:
                log.error(f"[HookSystem] 持久化钩子订阅失败: {e}")
            log.info(f"[HookSystem] 插件 {plugin_id} 注册事件: {event}")

    def unregister(self, event: str, plugin_id: str) -> None:
        """取消钩子订阅"""
        if event in self._handlers:
            self._handlers[event] = [h for h in self._handlers[event] if h.get("plugin_id") != plugin_id]
        try:
            self._repo.delete_hook(plugin_id, event)
        except Exception as e:
            log.error(f"[HookSystem] 删除钩子订阅失败: {e}")

    def unregister_all(self, plugin_id: str) -> None:
        """取消插件的所有钩子订阅"""
        for event in list(self._handlers.keys()):
            self._handlers[event] = [h for h in self._handlers[event] if h.get("plugin_id") != plugin_id]
        try:
            self._repo.delete_hooks_by_plugin(plugin_id)
        except Exception as e:
            log.error(f"[HookSystem] 删除插件钩子订阅失败: {e}")

    def emit(self, event: str, data: dict | None = None) -> None:
        """触发事件"""
        if event not in self._handlers:
            return

        handlers = self._handlers.get(event, [])
        if not handlers:
            return

        log.debug(f"[HookSystem] 触发事件: {event}, 订阅数: {len(handlers)}")
        for h in handlers:
            plugin_id = h.get("plugin_id")
            if not plugin_id:
                continue
            try:
                sandbox = container.plugin_sandbox()
                sandbox.call_hook(str(plugin_id), event, data or {})
            except Exception as e:
                log.error(f"[HookSystem] 插件 {plugin_id} 处理事件 {event} 失败: {e}")

    @property
    def EVENTS(self) -> list[str]:
        """列出所有已注册的事件名"""
        return list(self._handlers.keys())

    def list_subscriptions(self, plugin_id: str | None = None) -> list[dict]:
        """列出钩子订阅"""
        result = []
        for event, handlers in self._handlers.items():
            for h in handlers:
                if plugin_id and h.get("plugin_id") != plugin_id:
                    continue
                result.append(
                    {
                        "event": event,
                        "plugin_id": h.get("plugin_id"),
                    }
                )
        return result

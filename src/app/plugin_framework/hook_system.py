"""
Hook System - 全局事件钩子系统
插件通过注册钩子来响应系统事件
"""

from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import log
from app.db.repositories.plugin_framework_repository import PluginFrameworkRepository

if TYPE_CHECKING:
    from app.plugin_framework.sandbox import PluginSandbox


class HookSystem:
    """全局事件钩子系统——插件可自由注册任意事件，无白名单限制.

    由 lifespan 通过 AppContext 创建并管理生命周期。
    emit 默认同步执行；可通过 executor 参数启用线程池异步投递。
    """

    def __init__(
        self,
        plugin_sandbox: "PluginSandbox | None" = None,
        repo: PluginFrameworkRepository | None = None,
        executor: ThreadPoolExecutor | None = None,
    ):

        self._plugin_sandbox = plugin_sandbox
        self._repo = repo or PluginFrameworkRepository()
        self._handlers: dict[str, set[str]] = {}
        self._executor = executor
        self._load_from_db()

    def set_plugin_sandbox(self, plugin_sandbox: "PluginSandbox") -> None:
        """设置插件沙箱引用，用于处理循环依赖。"""
        self._plugin_sandbox = plugin_sandbox

    def _load_from_db(self):
        """从数据库加载钩子订阅"""
        try:
            records = self._repo.get_all_hooks()
            for r in records:
                event = getattr(r, "EVENT", None)
                plugin_id = getattr(r, "PLUGIN_ID", None)
                if event and plugin_id:
                    self._handlers.setdefault(event, set())
                    self._handlers[event].add(plugin_id)
        except Exception as e:
            log.warn(f"[HookSystem] 加载钩子订阅失败（可能表尚未创建）: {e}")

    def register(self, event: str, plugin_id: str) -> None:
        """注册钩子订阅——允许任意事件名"""
        self._handlers.setdefault(event, set())
        if plugin_id in self._handlers[event]:
            return
        self._handlers[event].add(plugin_id)
        try:
            self._repo.insert_hook(plugin_id, event)
        except Exception as e:
            log.error(f"[HookSystem] 持久化钩子订阅失败: {e}")
        log.info(f"[HookSystem] 插件 {plugin_id} 注册事件: {event}")

    def unregister(self, event: str, plugin_id: str) -> None:
        """取消钩子订阅"""
        handlers = self._handlers.get(event)
        if handlers:
            handlers.discard(plugin_id)
        try:
            self._repo.delete_hook(plugin_id, event)
        except Exception as e:
            log.error(f"[HookSystem] 删除钩子订阅失败: {e}")

    def unregister_all(self, plugin_id: str) -> None:
        """取消插件的所有钩子订阅"""
        for handlers in self._handlers.values():
            handlers.discard(plugin_id)
        try:
            self._repo.delete_hooks_by_plugin(plugin_id)
        except Exception as e:
            log.error(f"[HookSystem] 删除插件钩子订阅失败: {e}")

    def emit(self, event: str, data: dict | None = None) -> None:
        """触发事件.

        有 executor 时异步投递到线程池，无则同步串行调用。
        """
        handlers = self._handlers.get(event)
        if not handlers:
            return

        if self._plugin_sandbox is None:
            log.warn(f"[HookSystem] 插件沙箱尚未就绪，跳过事件: {event}")
            return

        log.debug(f"[HookSystem] 触发事件: {event}, 订阅数: {len(handlers)}")
        for plugin_id in handlers:
            if not plugin_id:
                continue
            if self._executor is not None:
                self._executor.submit(self._call_hook, plugin_id, event, data or {})
            else:
                self._call_hook(plugin_id, event, data or {})

    def _call_hook(self, plugin_id: str, event: str, data: dict) -> None:
        if self._plugin_sandbox is None:
            return
        try:
            self._plugin_sandbox.call_hook(str(plugin_id), event, data)
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
            for pid in handlers:
                if plugin_id and pid != plugin_id:
                    continue
                result.append(
                    {
                        "event": event,
                        "plugin_id": pid,
                    }
                )
        return result

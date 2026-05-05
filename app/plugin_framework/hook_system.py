# -*- coding: utf-8 -*-
"""
Hook System - 全局事件钩子系统
插件通过注册钩子来响应系统事件
"""
from typing import Dict, List

from app.db.repositories import PluginFrameworkRepository
from app.utils.commons import SingletonMeta
import log


class HookSystem(metaclass=SingletonMeta):
    """全局事件钩子系统"""

    EVENTS = [
        "plugin.install",
        "plugin.enable",
        "plugin.disable",
        "plugin.uninstall",
        "plugin.config_changed",
        "plugin.reload",
        "media.scraped",
        "media.transfered",
        "media.library_synced",
        "media.source_deleted",
        "media.douban_sync",
        "download.started",
        "download.completed",
        "download.failed",
        "download.removed",
        "site.signed_in",
        "site.statistics_updated",
        "site.cookie_sync",
        "site.local_storage_sync",
        "site.signin",
        "rss.subscribed",
        "rss.found",
        "rss.downloaded",
        "scheduler.tick",
        "system.startup",
        "system.shutdown",
        "webhook.emby",
        "webhook.jellyfin",
        "webhook.plex",
        "wework.login",
        "subtitle.download",
        "message.incoming",
        "subscribe.add",
        "subscribe.finished",
        "search.start",
        "transfer.fail",
        "library.file_deleted",
        "autoseed.start",
    ]

    def __init__(self):
        self._repo = PluginFrameworkRepository()
        self._handlers: Dict[str, List[dict]] = {}
        self._load_from_db()

    def _load_from_db(self):
        """从数据库加载钩子订阅"""
        try:
            records = self._repo.get_all_hooks()
            for r in records:
                event = getattr(r, 'EVENT', None)
                plugin_id = getattr(r, 'PLUGIN_ID', None)
                if event and plugin_id:
                    self._handlers.setdefault(event, [])
                    if plugin_id not in [h['plugin_id'] for h in self._handlers[event]]:
                        self._handlers[event].append({"plugin_id": plugin_id})
        except Exception as e:
            log.warn(f"[HookSystem] 加载钩子订阅失败（可能表尚未创建）: {e}")

    def register(self, event: str, plugin_id: str) -> None:
        """注册钩子订阅"""
        if event not in self.EVENTS:
            log.warn(f"[HookSystem] 未知事件类型: {event}")

        self._handlers.setdefault(event, [])
        if plugin_id not in [h['plugin_id'] for h in self._handlers[event]]:
            self._handlers[event].append({"plugin_id": plugin_id})
            try:
                self._repo.insert_hook(plugin_id, event)
            except Exception as e:
                log.error(f"[HookSystem] 持久化钩子订阅失败: {e}")
            log.info(f"[HookSystem] 插件 {plugin_id} 注册事件: {event}")

    def unregister(self, event: str, plugin_id: str) -> None:
        """取消钩子订阅"""
        if event in self._handlers:
            self._handlers[event] = [
                h for h in self._handlers[event]
                if h.get('plugin_id') != plugin_id
            ]
        try:
            self._repo.delete_hook(plugin_id, event)
        except Exception as e:
            log.error(f"[HookSystem] 删除钩子订阅失败: {e}")

    def unregister_all(self, plugin_id: str) -> None:
        """取消插件的所有钩子订阅"""
        for event in list(self._handlers.keys()):
            self._handlers[event] = [
                h for h in self._handlers[event]
                if h.get('plugin_id') != plugin_id
            ]
        try:
            self._repo.delete_hooks_by_plugin(plugin_id)
        except Exception as e:
            log.error(f"[HookSystem] 删除插件钩子订阅失败: {e}")

    def emit(self, event: str, data: dict = None) -> None:
        """触发事件"""
        if event not in self._handlers:
            return

        handlers = self._handlers.get(event, [])
        if not handlers:
            return

        log.debug(f"[HookSystem] 触发事件: {event}, 订阅数: {len(handlers)}")
        for h in handlers:
            plugin_id = h.get('plugin_id')
            try:
                from app.plugin_framework.sandbox import PluginSandbox
                sandbox = PluginSandbox()
                sandbox.call_hook(plugin_id, event, data or {})
            except Exception as e:
                log.error(f"[HookSystem] 插件 {plugin_id} 处理事件 {event} 失败: {e}")

    def list_subscriptions(self, plugin_id: str = None) -> List[dict]:
        """列出钩子订阅"""
        result = []
        for event, handlers in self._handlers.items():
            for h in handlers:
                if plugin_id and h.get('plugin_id') != plugin_id:
                    continue
                result.append({
                    "event": event,
                    "plugin_id": h.get('plugin_id'),
                })
        return result

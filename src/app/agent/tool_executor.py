"""Agent 工具执行器 — 按领域拆分为独立 handler 模块后的入口."""

import log
from app.agent.tools.base import ToolResult
from app.agent.tools.handlers_media import (
    media_download,
    media_search,
    media_subscribe,
    resource_filter,
)
from app.agent.tools.handlers_message_template import message_template
from app.agent.tools.handlers_system_command import system_command
from app.media.service import MediaService
from app.services.brush_service import BrushService
from app.services.downloader_core import DownloaderCore
from app.services.indexer_service import IndexerService
from app.services.rss_automation.task_service import RssTaskService
from app.services.search_service import Searcher
from app.services.site_service import SiteService
from app.services.subscribe.monitor import SubscriptionMonitor
from app.services.subscribe_service import SubscribeService
from app.services.sync_service import SyncService
from app.services.system.lifecycle import SystemLifecycleService
from app.services.torrentremover_core import TorrentRemoverService


class ToolExecutor:
    """工具执行器 — 桥接 Agent Tools 与业务 Service"""

    def __init__(
        self,
        message,
        thread_executor,
        scheduler_core,
        event_bus,
        download_monitor,
        filetransfer_service,
        rss_helper,
        search_intent_agent,
        site_userinfo,
        scheduler_service,
        message_client_service,
        sync_service: SyncService,
        subscription_monitor: SubscriptionMonitor,
        torrentremover_service: TorrentRemoverService,
        subscribe_service: SubscribeService,
        system_lifecycle_service: SystemLifecycleService,
        brush_service: BrushService,
        site_service: SiteService,
        rss_task_service: RssTaskService,
        media_service: MediaService,
        indexer_service: IndexerService,
        downloader_core: DownloaderCore,
        searcher: Searcher,
    ):
        self._message = message
        self._thread_executor = thread_executor
        self._scheduler_core = scheduler_core
        self._event_bus = event_bus
        self._download_monitor = download_monitor
        self._filetransfer_service = filetransfer_service
        self._rss_helper = rss_helper
        self._search_intent_agent = search_intent_agent
        self._site_userinfo = site_userinfo
        self._scheduler_service = scheduler_service
        self._message_client_service = message_client_service
        self._sync_service = sync_service
        self._subscription_monitor = subscription_monitor
        self._torrentremover_service = torrentremover_service
        self._subscribe_service = subscribe_service
        self._system_lifecycle_service = system_lifecycle_service
        self._brush_service = brush_service
        self._site_service = site_service
        self._rss_task_service = rss_task_service
        self._media_service = media_service
        self._indexer_service = indexer_service
        self._downloader_core = downloader_core
        self._searcher = searcher
        self._deps = {
            "message": message,
            "thread_executor": thread_executor,
            "scheduler_core": scheduler_core,
            "event_bus": event_bus,
            "download_monitor": download_monitor,
            "filetransfer_service": filetransfer_service,
            "rss_helper": rss_helper,
            "search_intent_agent": search_intent_agent,
            "site_userinfo": site_userinfo,
            "scheduler_service": scheduler_service,
            "message_client_service": message_client_service,
            "sync_service": sync_service,
            "subscription_monitor": subscription_monitor,
            "torrentremover_service": torrentremover_service,
            "subscribe_service": subscribe_service,
            "system_lifecycle_service": system_lifecycle_service,
            "brush_service": brush_service,
            "site_service": site_service,
            "rss_task_service": rss_task_service,
            "media_service": media_service,
            "indexer_service": indexer_service,
            "downloader_core": downloader_core,
            "searcher": searcher,
        }

    def execute(self, tool_name: str, **kwargs) -> ToolResult:
        """执行指定工具"""
        log.info(f"[ToolExecutor]执行工具: {tool_name}, 参数: {kwargs}")
        handler = getattr(self, f"_{tool_name}", None)
        if not handler:
            return ToolResult(success=False, error=f"未实现工具: {tool_name}")
        try:
            return handler(**kwargs)
        except Exception as e:
            log.error(f"[ToolExecutor]{tool_name} 执行失败: {e}")
            return ToolResult(success=False, error=str(e))

    def _system_command(self, **kwargs) -> ToolResult:
        return system_command(self._deps, **kwargs)

    def _message_template(self, **kwargs) -> ToolResult:
        return message_template(self._deps, **kwargs)

    def _media_search(self, **kwargs) -> ToolResult:
        return media_search(self._deps, **kwargs)

    def _resource_filter(self, **kwargs) -> ToolResult:
        return resource_filter(**kwargs)

    def _media_download(self, **kwargs) -> ToolResult:
        return media_download(self._deps, **kwargs)

    def _media_subscribe(self, **kwargs) -> ToolResult:
        return media_subscribe(self._deps, **kwargs)

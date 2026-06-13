"""Lifecycle services - 调度器与系统生命周期管理."""

import os
import subprocess

import log
from app.core.exceptions import ResourceNotFoundError
from app.infrastructure.thread import ThreadExecutor
from app.services.brush.task_service import BrushTaskService
from app.services.download_monitor import DownloadMonitor
from app.services.downloader_core import DownloaderCore
from app.services.downloader_core import DownloaderCore as Downloader
from app.services.file_index_service import FileIndexService
from app.services.rss_automation.task_service import RssTaskService
from app.services.scheduler.core import SchedulerCore
from app.services.subscribe.monitor import SubscriptionMonitor
from app.services.sync_engine import SyncEngine as Sync
from app.services.torrentremover_core import TorrentRemoverService
from initializer import (
    check_config,
    check_redis,
    init_default_categories,
    init_event_handlers,
    init_message_webhook_apikey,
    init_rbac_system,
    update_config,
    update_rss_state,
)


class SchedulerService:
    """
    系统调度业务服务
    负责启动各种后台服务（下载转移、目录同步、RSS下载、订阅搜索）
    """

    def __init__(
        self,
        downloader: Downloader | None = None,
        sync: Sync | None = None,
        thread_executor: ThreadExecutor | None = None,
        torrent_remover: TorrentRemoverService | None = None,
        subscription_monitor: SubscriptionMonitor | None = None,
    ):
        self._downloader = downloader
        self._sync = sync
        self._torrent_remover = torrent_remover
        self._subscription_monitor = subscription_monitor
        self._thread_executor = thread_executor
        self._commands = None

    @property
    def _command_map(self):
        if self._commands is None:
            self._commands = {
                "pttransfer": self._downloader.transfer if self._downloader else lambda: None,
                "sync": self._sync.transfer_sync if self._sync else lambda: None,
                "subscription_monitor": self._subscription_monitor.run if self._subscription_monitor else lambda: None,
                # 消息命令兼容映射
                "/ptt": self._downloader.transfer if self._downloader else lambda: None,
                "/ptr": self._torrent_remover.auto_remove_torrents if self._torrent_remover else lambda: None,
                "/rst": self._sync.transfer_sync if self._sync else lambda: None,
                "/sub": self._subscription_monitor.run if self._subscription_monitor else lambda: None,
            }
        return self._commands

    def start_service(self, item: str) -> str:
        """启动指定服务，失败时抛出异常"""
        command = self._command_map.get(item)
        if not command:
            raise ResourceNotFoundError("未知服务")
        if self._thread_executor:
            self._thread_executor.submit(command)
        return "服务已启动"


class SystemLifecycleService:
    """
    系统生命周期管理服务（原 app/system_service.py 顶层函数提取）
    职责：统一管理系统各服务的启动、停止、重启。
    """

    def __init__(
        self,
        scheduler_core: SchedulerCore,
        download_monitor: DownloadMonitor,
        sync: Sync,
        brush_task_service: BrushTaskService | None,
        rss_checker: RssTaskService | None,
        torrent_remover: TorrentRemoverService | None,
        downloader: DownloaderCore | None,
        file_index_service: FileIndexService | None,
        subscription_monitor: SubscriptionMonitor | None = None,
        site_userinfo=None,
        subscribe_service=None,
        media_server=None,
        thread_executor=None,
        apikey_service=None,
        hook_system=None,
    ):
        self._scheduler = scheduler_core
        self._sync = sync
        self._brush = brush_task_service
        self._rss_checker = rss_checker
        self._torrent_remover = torrent_remover
        self._downloader = downloader
        self._file_index = file_index_service
        self._download_monitor = download_monitor
        self._subscription_monitor = subscription_monitor
        self._site_userinfo = site_userinfo
        self._subscribe_service = subscribe_service
        self._media_server = media_server
        self._thread_executor = thread_executor
        self._apikey_service = apikey_service
        self._hook_system = hook_system

    @property
    def subscription_monitor(self) -> SubscriptionMonitor | None:
        return self._subscription_monitor

    def start_service(self) -> None:
        """启动所有后台服务（调度器优先启动，确保后续模块注册任务时调度器已就绪）"""
        # 0. 执行初始化（配置检查、RBAC、消息 webhook key 等）
        check_config()
        update_config()
        check_redis()
        update_rss_state()
        init_default_categories()
        init_rbac_system()
        init_event_handlers(hook_system=self._hook_system)
        init_message_webhook_apikey(apikey_service=self._apikey_service)
        # 1. 先启动调度器，确保所有后台服务的定时任务可以正常注册
        self._scheduler.start_service(
            load_defaults=True,
            thread_executor=self._thread_executor,
            site_userinfo=self._site_userinfo,
            subscription_monitor=self._subscription_monitor,
            media_server=self._media_server,
            sync_engine=self._sync,
            subscribe_service=self._subscribe_service,
        )
        # 2. 启动各业务服务（此时调度器已运行，init_config 里的 stop/start_job 可正常执行）
        if self._file_index:
            self._file_index.start()
        self._sync.init()
        if self._brush:
            self._brush.start_service()
        if self._rss_checker:
            self._rss_checker._refresh()
        if self._torrent_remover:
            self._torrent_remover.start_service()
        # 4. 启动下载完成实时监控（事件驱动转移）
        self._download_monitor.start()

    def stop_service(self) -> None:
        """停止所有后台服务"""
        self._scheduler.stop_service()
        if self._download_monitor:
            self._download_monitor.stop()
        if self._sync:
            self._sync.stop()
        if self._brush:
            self._brush.stop_service()
        if self._rss_checker:
            self._rss_checker.stop_service()
        if self._torrent_remover:
            self._torrent_remover.stop_service()
        if self._downloader:
            self._downloader.stop_service()
        if self._file_index:
            self._file_index.stop()

    def restart_service(self) -> None:
        """重启所有后台服务"""
        self.stop_service()
        self.start_service()

    def restart_server(self) -> None:
        """停止进程并重启服务器"""
        self.stop_service()
        script_path = os.path.join(os.getcwd(), "restart-server.sh")
        os.chmod(script_path, 0o700)
        res = subprocess.run(["bash", script_path], cwd=os.getcwd())
        if res.returncode == 0:
            log.info("Nexus Media 重启成功...")
        else:
            log.info(f"Nexus Media 重启失败: {res.stderr.decode()}")


def start_service(system_lifecycle_service: SystemLifecycleService) -> None:
    """启动所有后台服务（顶层兼容函数）"""
    system_lifecycle_service.start_service()


def stop_service(system_lifecycle_service: SystemLifecycleService) -> None:
    """停止所有后台服务（顶层兼容函数）"""
    system_lifecycle_service.stop_service()


def restart_service(system_lifecycle_service: SystemLifecycleService) -> None:
    """重启所有后台服务（顶层兼容函数）"""
    system_lifecycle_service.restart_service()


def restart_server(system_lifecycle_service: SystemLifecycleService) -> None:
    """重启服务器（顶层兼容函数）"""
    system_lifecycle_service.restart_server()

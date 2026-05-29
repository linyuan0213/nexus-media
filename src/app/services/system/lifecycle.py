"""Lifecycle services - 调度器与系统生命周期管理."""

import os
import subprocess

import log
from app.core.exceptions import ResourceNotFoundError
from app.di import container
from app.helper.thread_helper import ThreadHelper
from app.services.downloader_core import DownloaderCore as Downloader
from app.services.rss_core import Rss
from app.services.subscribe_service import SubscribeService as Subscribe
from app.services.sync_engine import SyncEngine as Sync
from initializer import (
    check_config,
    check_redis,
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
        rss: Rss | None = None,
        subscribe: Subscribe | None = None,
        thread_helper: ThreadHelper | None = None,
        torrent_remover=None,
    ):
        self._downloader = downloader
        self._sync = sync
        self._rss = rss
        self._subscribe = subscribe
        self._torrent_remover = torrent_remover
        self._thread_helper = thread_helper or container.thread_helper()
        self._commands = None

    @property
    def _command_map(self):
        if self._commands is None:
            self._commands = {
                "pttransfer": (self._downloader or container.downloader_core()).transfer,
                "sync": (self._sync or container.sync_engine()).transfer_sync,
                "rssdownload": (self._rss or container.rss_core()).rssdownload,
                "subscribe_search_all": (self._subscribe or container.subscribe_service()).subscribe_search_all,
                # 消息命令兼容映射
                "/ptt": (self._downloader or container.downloader_core()).transfer,
                "/ptr": (self._torrent_remover or container.torrentremover_service()).auto_remove_torrents,
                "/rst": (self._sync or container.sync_engine()).transfer_sync,
                "/rss": (self._rss or container.rss_core()).rssdownload,
                "/ssa": (self._subscribe or container.subscribe_service()).subscribe_search_all,
            }
        return self._commands

    def start_service(self, item: str) -> str:
        """启动指定服务，失败时抛出异常"""
        command = self._command_map.get(item)
        if not command:
            raise ResourceNotFoundError("未知服务")
        self._thread_helper.start_thread(command, ())
        return "服务已启动"


class SystemLifecycleService:
    """
    系统生命周期管理服务（原 app/system_service.py 顶层函数提取）
    职责：统一管理系统各服务的启动、停止、重启。
    """

    def __init__(
        self,
        scheduler_core=None,
        sync=None,
        brush_task_service=None,
        rss_checker=None,
        torrent_remover=None,
        downloader=None,
        plugin_manager=None,
        file_index_service=None,
    ):
        self._scheduler = scheduler_core or container.scheduler_core()
        # 保存外部注入的依赖（测试时传入 mock），不在 __init__ 中实例化
        self._sync = sync
        self._brush = brush_task_service
        self._rss_checker = rss_checker
        self._torrent_remover = torrent_remover
        self._downloader = downloader
        self._file_index = file_index_service

    def start_service(self) -> None:
        """启动所有后台服务（调度器优先启动，确保后续模块注册任务时调度器已就绪）"""
        # 0. 执行初始化（配置检查、RBAC、消息 webhook key 等）
        check_config()
        update_config()
        check_redis()
        update_rss_state()
        init_rbac_system()
        init_message_webhook_apikey()
        # 1. 先启动调度器，确保所有后台服务的定时任务可以正常注册
        self._scheduler.start_service(load_defaults=True)
        # 2. 加载基础组件
        container.site_conf()
        # 3. 启动各业务服务（此时调度器已运行，init_config 里的 stop/start_job 可正常执行）
        if self._sync is None:
            self._sync = container.sync_engine()
        if self._brush is None:
            self._brush = container.brush_task_service()
        if self._rss_checker is None:
            self._rss_checker = container.rss_task_service()
        if self._torrent_remover is None:
            self._torrent_remover = container.torrentremover_service()
        if self._downloader is None:
            self._downloader = container.downloader_core()
        if self._file_index is None:
            self._file_index = container.file_index_service()
        self._file_index.start()
        self._sync.init()
        self._brush.start_service()
        self._rss_checker._refresh()
        self._torrent_remover.start_service()

    def stop_service(self) -> None:
        """停止所有后台服务"""
        self._scheduler.stop_service()
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

    @staticmethod
    def restart_server() -> None:
        """停止进程并重启服务器"""
        SystemLifecycleService().stop_service()
        script_path = os.path.join(os.getcwd(), "restart-server.sh")
        os.chmod(script_path, 0o700)
        res = subprocess.run(["bash", script_path], cwd=os.getcwd())
        if res.returncode == 0:
            log.info("Nexus Media 重启成功...")
        else:
            log.info(f"Nexus Media 重启失败: {res.stderr.decode()}")


def start_service():
    """启动所有后台服务（顶层兼容函数）"""
    SystemLifecycleService().start_service()


def stop_service():
    """停止所有后台服务（顶层兼容函数）"""
    SystemLifecycleService().stop_service()


def restart_service():
    """重启所有后台服务（顶层兼容函数）"""
    SystemLifecycleService().restart_service()


def restart_server():
    """重启服务器（顶层兼容函数）"""
    SystemLifecycleService.restart_server()

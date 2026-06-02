"""下载监控服务 — 高频轮询检测下载完成，触发事件驱动转移."""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import log
from app.core.constants import PT_TAG
from app.di import container
from app.downloader.client_factory import DownloadClientFactory
from app.events import Event
from app.events.constants import DOWNLOAD_COMPLETED


class DownloadMonitor:
    """下载完成监控器.

    高频轮询（默认 30 秒）下载器状态，检测新完成的任务并发布 download.completed 事件，
    驱动 FileTransferService 实时转移。配合低频 pttransfer（30 分钟）兜底。
    """

    def __init__(
        self,
        client_factory: DownloadClientFactory | None = None,
        interval: int = 30,
        max_workers: int = 4,
    ):
        self._client_factory = client_factory or container.download_client_factory()
        self._interval = interval
        self._max_workers = max_workers
        self._event_bus = container.event_bus()
        self._processed_ids: set[str] = set()
        self._executor: ThreadPoolExecutor | None = None
        self._running = False

    def start(self) -> None:
        """启动监控线程池."""
        self.stop()
        self._running = True
        self._executor = ThreadPoolExecutor(
            max_workers=self._max_workers,
            thread_name_prefix="DownloadMonitor",
        )
        # 预热：记录当前所有已完成任务
        self._warmup()
        # 提交监控循环任务
        self._executor.submit(self._monitor_loop)
        log.info(f"[DownloadMonitor]下载完成监控已启动，轮询间隔: {self._interval}秒，并发数: {self._max_workers}")

    def stop(self) -> None:
        """优雅停止监控线程池."""
        if not self._running:
            return
        self._running = False
        if self._executor:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None
        log.info("[DownloadMonitor]下载完成监控已停止")

    def _monitor_loop(self) -> None:
        """监控主循环 — 在独立线程中运行，每次循环提交并发检查任务."""
        while self._running:
            try:
                self._check_all_downloaders_concurrent()
            except Exception as e:
                log.error(f"[DownloadMonitor]检查下载器异常: {e!s}")
            time.sleep(self._interval)

    def _warmup(self) -> None:
        """预热：记录当前所有已完成任务 ID，避免启动时大量触发."""
        try:
            for did in self._client_factory.monitor_downloader_ids:
                client = self._client_factory.get_client(did)
                if not client:
                    continue
                torrents, _ = client.get_torrents(status="completed")
                if torrents:
                    for torrent in torrents:
                        if torrent.id:
                            self._processed_ids.add(self._make_id(did, torrent.id))
        except Exception as e:
            log.warn(f"[DownloadMonitor]预热失败: {e!s}")

    def _check_all_downloaders_concurrent(self) -> None:
        """并发检查所有下载器的新完成任务."""
        if not self._executor:
            return

        monitor_ids = list(self._client_factory.monitor_downloader_ids)
        if not monitor_ids:
            return

        futures = {self._executor.submit(self._check_downloader, did): did for did in monitor_ids}

        for future in as_completed(futures):
            did = futures[future]
            try:
                future.result()
            except Exception as e:
                log.error(f"[DownloadMonitor]检查下载器 {did} 异常: {e!s}")

    def _check_downloader(self, did: str) -> None:
        """检查单个下载器的新完成任务."""
        client = self._client_factory.get_client(did)
        if not client:
            return

        downloader_conf = self._client_factory.get_downloader_conf(did)
        if not downloader_conf:
            return

        only_nexus_media = downloader_conf.get("only_nexus_media")
        match_path = downloader_conf.get("match_path")

        trans_tasks = client.get_transfer_task(tag=PT_TAG if only_nexus_media else None, match_path=match_path)
        if not trans_tasks:
            return

        for task in trans_tasks:
            task_id = task.get("id")
            task_path = task.get("path") or ""
            if not task_id or not task_path:
                continue

            uid = self._make_id(did, task_id)
            if uid in self._processed_ids:
                continue

            self._processed_ids.add(uid)
            self._publish_completed(did, task_id, task_path, task)

    def _make_id(self, downloader_id: str, task_id: str) -> str:
        """生成唯一任务标识."""
        return f"{downloader_id}:{task_id}"

    def _publish_completed(self, downloader_id: str, task_id: str, task_path: str, task: dict) -> None:
        """发布 download.completed 事件."""
        self._event_bus.publish(
            Event(
                event_type=DOWNLOAD_COMPLETED,
                payload={
                    "downloader_id": downloader_id,
                    "task_id": task_id,
                    "path": task_path,
                    "tags": task.get("tags"),
                    "name": task.get("name"),
                },
            )
        )
        log.info(f"[DownloadMonitor]检测到下载完成: {task_id} @ {task_path}")

    def mark_processed(self, downloader_id: str, task_id: str) -> None:
        """手动标记任务已处理（用于兜底扫描后去重）."""
        self._processed_ids.add(self._make_id(downloader_id, task_id))

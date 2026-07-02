"""下载监控服务 — 高频轮询检测下载完成，触发事件驱动转移."""

import time
from concurrent.futures import as_completed

import log
from app.core.constants import PT_TAG
from app.downloader.client_factory import DownloadClientFactory
from app.events import Event, EventBus
from app.events.constants import DOWNLOAD_COMPLETED
from app.events.payloads import DownloadCompletedPayload
from app.infrastructure.thread import ThreadExecutor


class DownloadMonitor:
    """下载完成监控器.

    高频轮询（默认 30 秒）下载器状态，检测新完成的任务并发布 download.completed 事件，
    驱动 FileTransferService 实时转移。配合低频 pttransfer（30 分钟）兜底。

    由 lifespan 通过 AppContext 创建并管理生命周期。
    """

    def __init__(
        self,
        client_factory: DownloadClientFactory,
        event_bus: EventBus,
        interval: int = 30,
        max_workers: int = 4,
    ):
        self._client_factory = client_factory
        self._interval = interval
        self._max_workers = max_workers
        self._event_bus = event_bus
        self._processed_ids: set[str] = set()
        self._executor: ThreadExecutor | None = None
        self._running = False
        self._last_snapshot: dict[str, set[str]] = {}

    def start(self) -> None:
        """启动监控线程池."""
        self.stop()
        self._running = True
        self._executor = ThreadExecutor(
            max_workers=self._max_workers,
            name="DownloadMonitor",
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
            self._executor.shutdown(wait=False)
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
        """预热：记录当前所有可转移任务 ID，避免启动时大量触发."""
        try:
            for did in self._client_factory.monitor_downloader_ids:
                client = self._client_factory.get_client(did)
                if not client:
                    continue
                downloader_conf = self._client_factory.get_downloader_conf(did)
                if not downloader_conf:
                    continue
                only_nexus_media = downloader_conf.get("only_nexus_media")
                match_path = downloader_conf.get("match_path")
                tag = PT_TAG if only_nexus_media else None
                trans_tasks = client.get_transfer_task(tag=tag, match_path=match_path)
                for task in trans_tasks:
                    if task.get("id"):
                        self._processed_ids.add(self._make_id(did, str(task.get("id"))))
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
        """检查单个下载器的新完成任务（增量检查）."""
        client = self._client_factory.get_client(did)
        if not client:
            return

        downloader_conf = self._client_factory.get_downloader_conf(did)
        if not downloader_conf:
            return

        only_nexus_media = downloader_conf.get("only_nexus_media")
        match_path = downloader_conf.get("match_path")
        tag = PT_TAG if only_nexus_media else None

        previous_ids = self._last_snapshot.get(did, set())
        if not previous_ids:
            # 首次全量拉取并建立快照
            trans_tasks = client.get_transfer_task(tag=tag, match_path=match_path)
            self._last_snapshot[did] = {str(task.get("id")) for task in trans_tasks if task.get("id")}
            self._emit_new_tasks(did, trans_tasks)
            return

        # 后续只拉取增量任务：先获取全部候选 id 列表，再针对新增 id 调用详情接口
        all_tasks = client.get_transfer_task(tag=tag, match_path=match_path)
        current_ids = {str(task.get("id")) for task in all_tasks if task.get("id")}
        new_ids = current_ids - previous_ids
        self._last_snapshot[did] = current_ids

        if not new_ids:
            return

        new_tasks = client.get_transfer_task(tag=tag, match_path=match_path, ids=list(new_ids))
        self._emit_new_tasks(did, new_tasks)

    def _emit_new_tasks(self, did: str, trans_tasks: list[dict]) -> None:
        """发布新增下载完成任务事件."""
        for task in trans_tasks:
            task_id = str(task.get("id")) if task.get("id") else ""
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
                payload=DownloadCompletedPayload(
                    downloader_id=downloader_id,
                    task_id=task_id,
                    path=task_path,
                    tags=task.get("tags"),
                    name=task.get("name"),
                ),
            )
        )
        log.info(f"[DownloadMonitor]检测到下载完成: {task_id} @ {task_path}")

    def refresh_factory(self) -> None:
        """刷新工厂缓存，在下载器/下载设置变更后调用."""
        self._client_factory._refresh()

    def mark_processed(self, downloader_id: str, task_id: str) -> None:
        """手动标记任务已处理（用于兜底扫描后去重）."""
        self._processed_ids.add(self._make_id(downloader_id, task_id))

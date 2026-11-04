"""转移任务队列 — download.completed 事件的持久化转移入口."""

from __future__ import annotations

import os
from typing import Any

import log
from app.core.settings import settings
from app.db.repositories.lifecycle_repository import LifecycleRepository
from app.domain.entities.transfer_task import SourceType, TransferTask
from app.domain.lifecycle import LifecycleStage, LifecycleStatus
from app.infrastructure.task_queue import Task, TaskQueue, TaskStatus, TaskWorker, create_task_queue
from app.services.identity_resolver import IdentityResolver
from app.services.lifecycle_service import LifecycleProjector


class TransferQueueService:
    """将下载完成转移放入持久队列，按固定并发执行."""

    def __init__(
        self,
        pipeline: Any,
        client_factory: Any,
        *,
        max_workers: int = 2,
        queue_name: str = "transfer",
        lifecycle: LifecycleProjector | None = None,
    ):
        self._pipeline = pipeline
        self._client_factory = client_factory
        self._lifecycle = lifecycle
        self._max_workers = max(1, int(max_workers))
        self._queue_name = queue_name
        self._queue: TaskQueue | None = None
        self._worker: TaskWorker | None = None
        self._failed = False

    def start(self) -> None:
        if self._queue is not None or self._failed:
            return
        configured = settings.queue.sync_workers if self._queue_name == "sync" else settings.queue.transfer_workers
        self._max_workers = max(1, int(configured))
        try:
            self._queue = create_task_queue(self._queue_name)
            self._worker = TaskWorker(
                self._queue,
                {"transfer.task": self._handle_task},
                consumer=f"transfer-{os.getpid()}",
                concurrency=self._max_workers,
                poll_block_ms=1000,
            )
            self._worker.start()
            log.info(f"[TransferQueue]转移队列已启动 queue={self._queue_name} durable={self._queue.durable}")
        except Exception as exc:  # noqa: BLE001
            self._failed = True
            log.warn(f"[TransferQueue]转移队列不可用，事件将回退直连: {exc}")

    def restart(self) -> None:
        """配置热重载：按新并发重建 worker."""
        self.stop()
        self.start()

    def stop(self) -> None:
        self._failed = False
        if self._worker is not None:
            self._worker.stop()
            self._worker = None
        if self._queue is not None:
            self._queue.close()
            self._queue = None

    def submit(self, payload: dict[str, Any]) -> bool:
        self.start()
        if self._queue is None:
            return False
        if self._is_library_done(payload):
            log.info(f"[TransferQueue]跳过已入库的重复转移: {payload.get('downloader_id')}:{payload.get('task_id')}")
            return True
        dedup = str(payload.get("dedup_key") or f"{payload.get('downloader_id')}:{payload.get('task_id')}")
        try:
            task = self._queue.enqueue("transfer.task", payload, dedup_key=dedup)
            if task.status.terminal:
                if task.status == TaskStatus.SUCCEEDED:
                    log.info(f"[TransferQueue]跳过已成功的重复转移任务 {task.id}")
                    return True
                # 失败/死信/取消不视为幂等成功，允许创建一次新的重试任务。
                task = self._queue.enqueue("transfer.task", payload, dedup_key=f"{dedup}:retry:{task.id}")
                if task.status.terminal:
                    log.warn(f"[TransferQueue]重试任务仍处于终态 {task.id} status={task.status.value}")
                    return False
            self._record(payload, LifecycleStage.TRANSFER_QUEUED, LifecycleStatus.QUEUED, "transfer.queued", task)
            return True
        except Exception as exc:  # noqa: BLE001
            log.warn(f"[TransferQueue]入队失败，回退直连: {exc}")
            return False

    def _is_library_done(self, payload: dict[str, Any]) -> bool:
        identity_id = str(payload.get("identity_id") or "")
        if not identity_id:
            return False
        repo = LifecycleRepository()
        season = int(payload.get("season") or 0)
        episode = int(payload.get("episode") or 0)
        current = repo.get_current(identity_id, season=season, episode=episode)
        if current is None:
            # 只有电影/无季集任务才允许用聚合状态；分集或季包不能被整部聚合状态跳过。
            if season or episode:
                return False
            current = repo.get_grouped_identity(identity_id)
        stage = (
            str(current.get("STAGE") or "") if isinstance(current, dict) else str(getattr(current, "STAGE", "") or "")
        )
        status = (
            str(current.get("STATUS") or "") if isinstance(current, dict) else str(getattr(current, "STATUS", "") or "")
        )
        return stage == LifecycleStage.IN_LIBRARY.value and status == LifecycleStatus.SUCCEEDED.value

    def _handle_task(self, task: Task) -> dict[str, Any]:
        payload = task.payload
        if self._is_library_done(payload):
            log.info(f"[TransferQueue]跳过已入库的旧转移任务 {task.id} identity={payload.get('identity_id')}")
            return {"success": True, "skipped": True}
        downloader_id = str(payload.get("downloader_id") or "")
        task_id = str(payload.get("task_id") or "")
        source_type_value = str(payload.get("source_type") or SourceType.DOWNLOADER.value)
        source_type = SourceType.DIRECTORY if source_type_value == SourceType.DIRECTORY.value else SourceType.DOWNLOADER
        client = self._client_factory.get_client(downloader_id) if downloader_id else None
        tags = payload.get("tags")
        post_process = None
        if source_type == SourceType.DOWNLOADER:

            def _post_process(_task: TransferTask, success: bool, msg: str) -> None:
                if not success:
                    # 失败保持原标签，保留 30 分钟兜底扫描和重启后的重试机会。
                    log.warn(f"[TransferQueue]任务 {task_id} 转移失败: {msg}")
                    return
                if payload.get("operation") == "move":
                    log.info(f"[TransferQueue]移动模式删除种子: {task_id}")
                    if client:
                        client.delete_torrents(delete_file=True, ids=task_id)
                elif client:
                    client.set_torrents_status(ids=task_id, tags=tags)

            post_process = _post_process

        transfer_task = TransferTask(
            source_type=source_type,
            source_id=str(payload.get("source_id") or payload.get("name") or ""),
            file_paths=list(payload.get("file_paths") or [payload.get("path") or ""]),
            operation=str(payload.get("operation") or ""),
            target_dir=payload.get("target_dir"),
            unknown_dir=payload.get("unknown_dir"),
            dst_backend_id=str(payload.get("dst_backend_id") or "local"),
            provider_data=payload.get("provider_data"),
            media_type=payload.get("media_type"),
            season=payload.get("season"),
            fallback_episode=payload.get("fallback_episode"),
            post_process=post_process,
        )
        self._record(payload, LifecycleStage.TRANSFERRING, LifecycleStatus.RUNNING, "transfer.started", task)
        success, message = self._pipeline.process(transfer_task)
        if not success:
            self._record(
                payload,
                LifecycleStage.TRANSFERRING,
                LifecycleStatus.FAILED,
                "transfer.failed",
                task,
                error=message,
            )
            raise RuntimeError(message or "转移失败")
        self._record(payload, LifecycleStage.TRANSFERRED, LifecycleStatus.SUCCEEDED, "transfer.completed", task)
        return {"success": True, "message": message}

    def _record(
        self,
        payload: dict[str, Any],
        stage: LifecycleStage,
        status: LifecycleStatus,
        event_type: str,
        task: Task,
        *,
        error: str | None = None,
    ) -> None:
        if self._lifecycle is None:
            return
        media_type = str(payload.get("media_type") or "movie")
        season = int(payload.get("season") or 0)
        resolved = IdentityResolver().resolve_values(
            identity_id=payload.get("identity_id"),
            provider=payload.get("anchor_provider") or payload.get("source_provider"),
            external_id=payload.get("anchor_external_id"),
            title=payload.get("title"),
            year=payload.get("year"),
            media_type=media_type,
            content_profile=payload.get("content_profile"),
            season=season,
            allow_local=True,
        )
        identity_id = resolved.identity_id
        if not identity_id:
            return
        try:
            self._lifecycle.record(
                identity_id=identity_id,
                stage=stage,
                status=status,
                event_type=event_type,
                media_type=media_type,
                season=season,
                episode=int(payload.get("episode") or 0),
                run_id=payload.get("run_id") or f"transfer:{payload.get('task_id')}",
                trace_id=payload.get("trace_id") or f"identity:{identity_id}",
                title=payload.get("title"),
                year=payload.get("year"),
                poster=payload.get("poster"),
                source_provider=payload.get("source_provider"),
                content_profile=payload.get("content_profile"),
                user_id=payload.get("user_id"),
                retry_count=task.attempts,
                error=error,
                payload={"queue": task.queue_name, "task_id": task.id, "source_task_id": payload.get("task_id")},
                event_key=f"transfer:{task.id}:{event_type}:{task.attempts}",
            )
        except Exception as exc:  # noqa: BLE001
            log.warn(f"[Lifecycle]记录转移生命周期失败: {exc}")

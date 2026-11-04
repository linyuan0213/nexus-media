"""刮削任务服务 — 转移后的单文件/目录刮削通过持久队列执行."""

from __future__ import annotations

import os
from typing import Any

import log
from app.core.settings import settings
from app.db.repositories.storage_backend_repo_adapter import StorageBackendRepositoryAdapter
from app.domain.lifecycle import LifecycleStage, LifecycleStatus
from app.domain.mediatypes import MediaType
from app.events import Event
from app.events.bus import EventBus
from app.events.constants import MEDIA_EPISODE_TRANSFERRED, MEDIA_TRANSFER_FINISHED, SUBTITLE_DOWNLOAD
from app.events.payloads import MediaEpisodeTransferredPayload, MediaTransferFinishedPayload, SubtitleDownloadPayload
from app.infrastructure.task_queue import QueueUnavailableError, Task, TaskQueue, TaskWorker, create_task_queue
from app.infrastructure.thread import ThreadExecutor
from app.media.models import MediaInfo
from app.media.scraper import Scraper
from app.services.lifecycle_service import LifecycleProjector
from app.storage.backends.base import StorageBackend, StorageType
from app.storage.config_models import LocalStorageConfig
from app.storage.factory import StorageBackendFactory
from app.utils import ExceptionUtils
from app.utils.json_utils import JsonUtils


class ScrapeQueueService:
    """刮削执行服务.

    - submit_file_scrape：入队 scrape.file，成功后发布 transfer_finished
    - submit_folder_scrape：入队 scrape.folder
    - Redis 队列不可用时回退进程内线程池，不阻塞转移线程
    """

    def __init__(
        self,
        scraper: Scraper,
        max_workers: int = 3,
        *,
        message: Any = None,
        event_bus: EventBus | None = None,
        queue_name: str = "scrape",
        lifecycle: LifecycleProjector | None = None,
    ):
        self._scraper = scraper
        self._max_workers = max(1, int(max_workers))
        self._message = message
        self._event_bus = event_bus
        self._lifecycle = lifecycle
        self._queue_name = queue_name
        self._queues: dict[str, TaskQueue] = {}
        self._workers: list[TaskWorker] = []
        self._executor = ThreadExecutor.named("scrape", max_workers=max_workers)
        self._started = False

    def start(self) -> None:
        """启动 file/folder 两个独立刮削队列；失败时保留线程池兜底."""
        if self._started:
            return
        self._started = True
        self._max_workers = max(1, int(settings.queue.scrape_workers))
        plans = (
            ("file", max(1, min(2, self._max_workers)), "scrape.file", self._run_file_task),
            ("folder", self._max_workers, "scrape.folder", self._run_folder_task),
        )
        for suffix, workers, task_type, handler in plans:
            try:
                queue = create_task_queue(f"{self._queue_name}:{suffix}")
                worker = TaskWorker(
                    queue,
                    {task_type: handler},
                    consumer=f"scrape-{suffix}-{os.getpid()}",
                    concurrency=workers,
                    poll_block_ms=1000,
                )
                worker.start()
                self._queues[suffix] = queue
                self._workers.append(worker)
                log.info(
                    f"[ScrapeQueue]刮削队列已启动 queue={self._queue_name}:{suffix} "
                    f"concurrency={workers} durable={queue.durable}"
                )
            except QueueUnavailableError as exc:
                log.warn(f"[ScrapeQueue]刮削队列 {suffix} 不可用，回退线程池: {exc}")
            except Exception as exc:  # noqa: BLE001
                log.warn(f"[ScrapeQueue]刮削队列 {suffix} 启动失败，回退线程池: {exc}")

    def restart(self) -> None:
        """配置热重载：只重建 worker，不关闭线程池."""
        self.stop(shutdown_executor=False)
        self.start()

    def stop(self, shutdown_executor: bool = True) -> None:
        self._started = False
        for worker in self._workers:
            worker.stop()
        for queue in self._queues.values():
            queue.close()
        self._workers.clear()
        self._queues.clear()
        if shutdown_executor:
            self._executor.shutdown()

    def submit_file_scrape(
        self,
        media,
        dir_path: str,
        file_name: str,
        file_ext: str,
        dst_backend=None,
        finalize: dict[str, Any] | None = None,
    ) -> None:
        """提交单文件刮削；成功后由任务发布最终转移事件."""
        payload = {
            "media": JsonUtils.model_to_jsonable(media),
            "dir_path": dir_path,
            "file_name": file_name,
            "file_ext": file_ext,
            "backend_id": str(getattr(dst_backend, "id", "") or ""),
            "finalize": finalize or {},
        }
        dedup = self._file_dedup_key(dir_path, file_name, file_ext, finalize)
        task = self._enqueue("file", "scrape.file", payload, dedup)
        if task is not None:
            self._record_media(media, LifecycleStage.SCRAPE_QUEUED, LifecycleStatus.QUEUED, "scrape.queued", task)
            return
        # 队列不可用时仍异步执行，避免阻塞转移
        self._executor.submit(self._run_file_payload, payload, None)

    def submit_folder_scrape(self, path: str, dst_backend=None, mode: str = "force_all") -> None:
        payload = {
            "path": path,
            "backend_id": str(getattr(dst_backend, "id", "") or ""),
            "mode": mode,
        }
        dedup = self._folder_dedup_key(path, mode)
        if self._enqueue("folder", "scrape.folder", payload, dedup) is not None:
            return
        self._executor.submit(self._run_folder_payload, payload, None)

    def _enqueue(self, suffix: str, task_type: str, payload: dict[str, Any], dedup_key: str) -> Task | None:
        self.start()
        queue = self._queues.get(suffix)
        if queue is None:
            return None
        try:
            return queue.enqueue(task_type, payload, dedup_key=dedup_key)
        except Exception as exc:  # noqa: BLE001
            log.warn(f"[ScrapeQueue]入队失败，回退线程池: {exc}")
            return None

    def _run_file_task(self, task: Task) -> dict[str, Any]:
        return self._run_file_payload(task.payload, task)

    def _run_file_payload(self, payload: dict[str, Any], task: Task | None) -> dict[str, Any]:
        media = MediaInfo.model_validate(payload["media"])
        backend = self._resolve_backend(payload.get("backend_id"))
        if task is not None:
            self._record_media(media, LifecycleStage.SCRAPING, LifecycleStatus.RUNNING, "scrape.started", task)
        ok = self._scrape_file(
            media,
            str(payload.get("dir_path") or ""),
            str(payload.get("file_name") or ""),
            str(payload.get("file_ext") or ""),
            backend,
        )
        finalize = payload.get("finalize") or {}
        if ok:
            self._finalize(media, finalize, metadata_ok=True)
            if task is not None:
                self._record_media(
                    media, LifecycleStage.SCRAPED, LifecycleStatus.SUCCEEDED, "scrape.completed", task, progress=100
                )
                # 刮削只发生在最终媒体库路径，完成即代表文件已入库。
                self._record_media(
                    media, LifecycleStage.IN_LIBRARY, LifecycleStatus.SUCCEEDED, "library.present", task, progress=100
                )
            return {"scraped": True}
        if task is not None:
            self._record_media(
                media,
                LifecycleStage.SCRAPING,
                LifecycleStatus.FAILED,
                "scrape.failed",
                task,
                error="刮削失败",
            )
        if task is None or task.attempts + 1 >= task.max_attempts:
            self._finalize(media, finalize, metadata_ok=False)
        raise RuntimeError(f"刮削失败: {payload.get('dir_path')}/{payload.get('file_name')}")

    def _run_folder_task(self, task: Task) -> dict[str, Any]:
        return self._run_folder_payload(task.payload, task)

    def _run_folder_payload(self, payload: dict[str, Any], task: Task | None) -> dict[str, Any]:
        path = str(payload.get("path") or "")
        backend = self._resolve_backend(payload.get("backend_id"))
        mode = str(payload.get("mode") or "force_all")
        try:
            self._scraper.folder_scraper(path=path, mode=mode, dst_backend=backend)
            return {"scraped": True}
        except Exception as exc:  # noqa: BLE001
            ExceptionUtils.exception_traceback(exc)
            raise RuntimeError(f"目录刮削失败 {path}: {exc}") from exc

    def _finalize(self, media: MediaInfo, finalize: dict[str, Any], *, metadata_ok: bool) -> None:
        if not finalize or self._event_bus is None:
            return
        in_from = finalize.get("in_from")
        if metadata_ok and media.type == MediaType.MOVIE and self._message is not None:
            try:
                self._message.send_transfer_movie_message(
                    in_from,
                    media,
                    int(finalize.get("exist_filenum") or 0),
                    bool(finalize.get("category_flag")),
                )
            except Exception as exc:  # noqa: BLE001
                log.warn(f"[ScrapeQueue]发送入库消息失败: {exc}")

        file_ext = str(finalize.get("file_ext") or "")
        ret_file_path = str(finalize.get("ret_file_path") or "")
        if ret_file_path:
            self._event_bus.publish(
                Event(
                    event_type=SUBTITLE_DOWNLOAD,
                    payload=SubtitleDownloadPayload(
                        media_info=media.to_dict(),
                        file=ret_file_path,
                        file_ext=file_ext,
                        bluray=bool(finalize.get("bluray")),
                    ),
                )
            )
        self._event_bus.publish(
            Event(
                event_type=MEDIA_TRANSFER_FINISHED,
                payload=MediaTransferFinishedPayload(
                    in_path=str(finalize.get("in_path") or ""),
                    file=str(finalize.get("file_item") or ""),
                    target_path=str(finalize.get("out_path") or ""),
                    dest=str(finalize.get("dist_path") or ""),
                    media_info=media.to_dict(),
                ),
            )
        )
        if media.type in (MediaType.TV, MediaType.ANIME) and media.get_episode_list():
            self._event_bus.publish(
                Event(
                    event_type=MEDIA_EPISODE_TRANSFERRED,
                    payload=MediaEpisodeTransferredPayload(
                        tmdb_id=str(media.tmdb_id or ""),
                        title=str(media.title or ""),
                        season=media.get_season_seq(),
                        episodes=media.get_episode_list(),
                        total_episodes=media.total_episodes,
                        media_type=media.type.value if media.type else None,
                        anchor_provider=getattr(media, "anchor_provider", None),
                        anchor_external_id=getattr(media, "anchor_external_id", None),
                        identity_id=getattr(media, "identity_id", None),
                        content_profile=getattr(media, "content_profile", None),
                        user_id=getattr(media, "user_id", None),
                    ),
                )
            )

    def _scrape_file(self, media, dir_path, file_name, file_ext, dst_backend, *, force: bool = False) -> bool:
        try:
            result = self._scraper.gen_scraper_files(
                media=media,
                dir_path=dir_path,
                file_name=file_name,
                file_ext=file_ext,
                force=force,
                dst_backend=dst_backend,
            )
            return bool(result)
        except Exception as e:  # noqa: BLE001
            ExceptionUtils.exception_traceback(e)
            log.error(f"[ScrapeQueue]单文件刮削失败 {dir_path}/{file_name}: {e}")
            return False

    def _record_media(
        self,
        media: MediaInfo,
        stage: LifecycleStage,
        status: LifecycleStatus,
        event_type: str,
        task: Task | None,
        *,
        progress: int | None = None,
        error: str | None = None,
    ) -> None:
        if self._lifecycle is None:
            return
        try:
            self._lifecycle.record_media(
                media,
                stage=stage,
                status=status,
                event_type=event_type,
                run_id=(task.payload.get("run_id") if task else None) or (task.id if task else None),
                trace_id=(task.payload.get("trace_id") if task else None) or (task.id if task else None),
                progress=progress,
                retry_count=task.attempts if task else 0,
                error=error,
                payload={"queue": task.queue_name, "task_id": task.id} if task else {},
                event_key=f"scrape:{task.id}:{event_type}:{task.attempts}" if task else None,
            )
        except Exception as exc:  # noqa: BLE001
            log.warn(f"[Lifecycle]记录刮削生命周期失败: {exc}")

    def _resolve_backend(self, backend_id: str | None) -> StorageBackend | None:
        if not backend_id or backend_id == "local":
            return None
        try:
            entity = StorageBackendRepositoryAdapter().get_by_id(int(backend_id))
            if entity is None:
                return None
            info = StorageBackendFactory.get_config_info(entity.type)
            stype, cls = info if info else (StorageType.LOCAL, LocalStorageConfig)
            config = cls(id=str(entity.id), name=entity.name, type=stype, enabled=entity.enabled)
            for key, value in entity.config.items():
                if hasattr(config, key):
                    setattr(config, key, value)
            return StorageBackendFactory.create(config)
        except Exception as exc:  # noqa: BLE001
            log.warn(f"[ScrapeQueue]解析存储后端失败 {backend_id}: {exc}")
            return None

    @staticmethod
    def _file_dedup_key(dir_path: str, file_name: str, file_ext: str, finalize: dict[str, Any] | None) -> str:
        token = ""
        if finalize:
            token = f"{finalize.get('in_path', '')}|{finalize.get('file_item', '')}|{finalize.get('out_path', '')}"
        return f"file:{dir_path}|{file_name}|{file_ext}|{token}"

    @staticmethod
    def _folder_dedup_key(path: str, mode: str) -> str:
        try:
            mtime = int(os.stat(path).st_mtime) if path and os.path.exists(path) else 0
        except OSError:
            mtime = 0
        return f"folder:{path}|{mtime}|{mode}"

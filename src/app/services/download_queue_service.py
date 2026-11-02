"""下载队列服务 — 为 Thunder 等需要 Nexus 侧并发的下载器提供排队执行."""

from __future__ import annotations

import base64
import hashlib
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import log
from app.core.settings import settings
from app.domain.lifecycle import LifecycleStage, LifecycleStatus
from app.domain.mediatypes import MediaType
from app.infrastructure.task_queue import Task, TaskQueue, TaskWorker, create_task_queue
from app.media.models import MediaInfo
from app.services.lifecycle_service import LifecycleProjector
from app.utils.json_utils import JsonUtils

_MAX_QUEUED_TORRENT_BYTES = 20 * 1024 * 1024
_SLOT_POLL_SECONDS = 5.0


class DownloadQueueService:
    """按下载器串行准入的下载队列.

    当前只接管电影类 Thunder 下载：
    - 每个下载器一个队列 worker，worker concurrency=1
    - 执行前等待下载器活跃任务数低于 max_active_tasks（默认 Thunder=5）
    - 历史和任务 ID 在入队时先落 queued 占位，添加成功后更新为真实任务 ID
    """

    def __init__(
        self,
        pipeline: Any,
        client_factory: Any,
        history_repo: Any,
        lifecycle: LifecycleProjector | None = None,
    ):
        self._pipeline = pipeline
        self._client_factory = client_factory
        self._history_repo = history_repo
        self._lifecycle = lifecycle
        self._stacks: dict[str, tuple[TaskQueue, TaskWorker, int]] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def stop(self) -> None:
        """停止所有下载队列 worker；pending 任务留给下次启动恢复."""
        with self._guard:
            stacks = list(self._stacks.values())
            self._stacks.clear()
        for queue, worker, _ in stacks:
            try:
                worker.stop()
            finally:
                queue.close()

    def start(self) -> None:
        """启动所有已配置的 Nexus 队列下载器 worker，恢复重启前未完成任务."""
        try:
            confs = self._client_factory.get_downloader_conf()
        except Exception as exc:  # noqa: BLE001
            log.warn(f"[DownloadQueue]读取下载器配置失败: {exc}")
            return
        if not isinstance(confs, dict):
            return
        for downloader_id, conf in confs.items():
            if not isinstance(conf, dict) or not self._is_nexus_mode(conf):
                continue
            try:
                self._ensure_stack(str(downloader_id), self._max_active(str(downloader_id)))
            except Exception as exc:  # noqa: BLE001
                log.warn(f"[DownloadQueue]启动下载队列失败 downloader={downloader_id}: {exc}")

    def should_queue(self, media_info: Any, downloader_id: str | None) -> bool:
        """是否为该资源/下载器启用 Nexus 队列."""
        media_type = getattr(media_info, "type", None)
        media_type_value = getattr(media_type, "value", media_type)
        if not downloader_id or str(media_type_value or "").lower() != MediaType.MOVIE.value:
            return False
        conf = self._client_factory.get_downloader_conf(str(downloader_id))
        if not isinstance(conf, dict):
            return False
        return self._is_nexus_mode(conf)

    def submit(
        self,
        media_info: Any,
        *,
        downloader_id: str,
        is_paused: bool | None = None,
        tag: Any = None,
        download_dir: str | None = None,
        download_setting: str | None = None,
        upload_limit: Any = None,
        download_limit: Any = None,
        torrent_file: str | None = None,
        in_from: Any = None,
        user_name: str | None = None,
        proxy: Any = None,
        file_indices: Any = None,
        file_names: Any = None,
        user_id: int | None = None,
    ) -> Task | None:
        """写入 queued 历史并入队；失败返回 None 让调用方走直接下载."""
        task_id = uuid.uuid4().hex
        max_active = self._max_active(downloader_id)
        torrent_b64 = self._read_torrent(torrent_file)
        history_id = self._history_repo.insert_download_history(
            media_info=media_info,
            downloader=str(downloader_id),
            download_id=task_id,
            save_dir="",
            user_id=user_id,
            state="queued",
        )
        if not history_id:
            return None
        payload = {
            "media_info": JsonUtils.model_to_jsonable(media_info),
            "history_id": int(history_id),
            "run_id": task_id,
            "trace_id": task_id,
            "downloader_id": str(downloader_id),
            "max_active": max_active,
            "is_paused": is_paused,
            "tag": tag,
            "download_dir": download_dir,
            "download_setting": download_setting,
            "upload_limit": upload_limit,
            "download_limit": download_limit,
            "in_from": in_from,
            "user_name": user_name,
            "proxy": proxy,
            "file_indices": file_indices,
            "file_names": file_names,
            "user_id": user_id,
            "torrent_b64": torrent_b64,
            "torrent_name": os.path.basename(torrent_file) if torrent_file else "",
        }
        dedup_key = self._dedup_key(media_info, downloader_id, user_id, torrent_b64)
        try:
            queue, _, _ = self._ensure_stack(downloader_id, max_active)
            task = queue.enqueue(
                "download.add",
                payload,
                dedup_key=dedup_key,
                task_id=task_id,
            )
        except Exception:
            self._history_repo.delete_download_history_by_id(history_id)
            raise
        if task.id != task_id:
            # 幂等命中已有任务，删除本次占位历史
            self._history_repo.delete_download_history_by_id(history_id)
        else:
            self._record_media(
                media_info,
                LifecycleStage.DOWNLOAD_QUEUED,
                LifecycleStatus.QUEUED,
                "download.queued",
                task,
            )
        return task

    def _ensure_stack(self, downloader_id: str, max_active: int) -> tuple[TaskQueue, TaskWorker, int]:
        key = str(downloader_id)
        with self._guard:
            stack = self._stacks.get(key)
            if stack is not None:
                return stack
            queue = create_task_queue(f"download:{key}")
            worker = TaskWorker(
                queue,
                {"download.add": self._handle_task},
                consumer=f"download-{key}",
                concurrency=1,
                poll_block_ms=1000,
            )
            worker.start()
            stack = (queue, worker, max_active)
            self._stacks[key] = stack
            log.info(f"[DownloadQueue]下载队列已启动 downloader={key} max_active={max_active}")
            return stack

    def _handle_task(self, task: Task) -> dict[str, Any]:
        payload = task.payload
        media_info = MediaInfo.model_validate(payload["media_info"])
        downloader_id = str(payload["downloader_id"])
        history_id = int(payload["history_id"])
        max_active = int(payload.get("max_active") or self._max_active(downloader_id))
        torrent_path = self._materialize_torrent(task, payload)
        try:
            # 上一次执行已成功添加但 ACK 前崩溃时，直接复用真实任务 ID，避免重复下载
            existing = self._history_repo.get_download_history_by_row_id(history_id)
            if (
                existing is not None
                and existing.STATE in {"downloading", "completed"}
                and existing.DOWNLOAD_ID
                and existing.DOWNLOAD_ID != task.id
            ):
                return {"download_id": existing.DOWNLOAD_ID}
            self._record_media(
                media_info,
                LifecycleStage.DOWNLOADING,
                LifecycleStatus.RUNNING,
                "download.started",
                task,
            )
            self._wait_for_slot(downloader_id, max_active)
            with self._downloader_lock(downloader_id):
                self._wait_for_slot(downloader_id, max_active)
                _, download_id, error = self._pipeline.execute(
                    media_info=media_info,
                    is_paused=payload.get("is_paused"),
                    tag=payload.get("tag"),
                    download_dir=payload.get("download_dir"),
                    download_setting=payload.get("download_setting"),
                    downloader_id=downloader_id,
                    upload_limit=payload.get("upload_limit"),
                    download_limit=payload.get("download_limit"),
                    torrent_file=torrent_path,
                    in_from=payload.get("in_from"),
                    user_name=payload.get("user_name"),
                    proxy=payload.get("proxy"),
                    file_indices=payload.get("file_indices"),
                    file_names=payload.get("file_names"),
                    user_id=payload.get("user_id"),
                    history_id=history_id,
                )
            if not download_id:
                if task.attempts + 1 >= task.max_attempts:
                    self._history_repo.update_download_history_task(history_id, "", "", state="error")
                self._record_media(
                    media_info,
                    LifecycleStage.DOWNLOADING,
                    LifecycleStatus.FAILED,
                    "download.failed",
                    task,
                    error=error or "下载器添加任务失败",
                )
                raise RuntimeError(error or "下载器添加任务失败")
            self._record_media(
                media_info,
                LifecycleStage.DOWNLOADED,
                LifecycleStatus.SUCCEEDED,
                "download.completed",
                task,
                progress=100,
            )
            return {"download_id": download_id}
        finally:
            if torrent_path:
                try:
                    os.remove(torrent_path)
                except OSError:
                    pass

    def _record_media(
        self,
        media_info: MediaInfo,
        stage: LifecycleStage,
        status: LifecycleStatus,
        event_type: str,
        task: Task,
        *,
        progress: int | None = None,
        error: str | None = None,
    ) -> None:
        if self._lifecycle is None:
            return
        try:
            self._lifecycle.record_media(
                media_info,
                stage=stage,
                status=status,
                event_type=event_type,
                run_id=task.payload.get("run_id") or task.id,
                trace_id=task.payload.get("trace_id") or task.id,
                progress=progress,
                retry_count=task.attempts,
                error=error,
                payload={
                    "queue": task.queue_name,
                    "task_id": task.id,
                    "downloader_id": task.payload.get("downloader_id"),
                },
                event_key=f"download:{task.id}:{event_type}:{task.attempts}",
            )
        except Exception as exc:  # noqa: BLE001
            log.warn(f"[Lifecycle]记录下载生命周期失败: {exc}")

    def _wait_for_slot(self, downloader_id: str, max_active: int) -> None:
        client = self._client_factory.get_client(str(downloader_id))
        if client is None:
            raise RuntimeError(f"下载器 {downloader_id} 不可用")
        while True:
            try:
                torrents = client.get_downloading_torrents()
            except Exception as exc:  # noqa: BLE001
                log.warn(f"[DownloadQueue]查询活跃任务失败 downloader={downloader_id}: {exc}")
                time.sleep(_SLOT_POLL_SECONDS)
                continue
            if torrents is None:
                time.sleep(_SLOT_POLL_SECONDS)
                continue
            if len(torrents) < max_active:
                return
            time.sleep(_SLOT_POLL_SECONDS)

    def _is_nexus_mode(self, conf: dict[str, Any]) -> bool:
        ctype = str(conf.get("type") or "").lower()
        config_value = conf.get("config")
        config = config_value if isinstance(config_value, dict) else {}
        mode = str(conf.get("queue_mode") or config.get("queue_mode") or ("nexus" if ctype == "thunder" else "native"))
        return mode.lower() == "nexus"

    def _max_active(self, downloader_id: str | None) -> int:
        if not downloader_id:
            return 5
        conf = self._client_factory.get_downloader_conf(str(downloader_id))
        if not isinstance(conf, dict):
            return 5
        config_value = conf.get("config")
        config = config_value if isinstance(config_value, dict) else {}
        ctype = str(conf.get("type") or "").lower()
        default = 5 if ctype == "thunder" else 1
        raw = conf.get("max_active_tasks") or config.get("max_active_tasks") or default
        try:
            return max(1, int(raw))
        except (TypeError, ValueError):
            return default

    def _read_torrent(self, torrent_file: str | None) -> str:
        if not torrent_file or not os.path.isfile(torrent_file):
            return ""
        path = Path(torrent_file)
        if path.stat().st_size > _MAX_QUEUED_TORRENT_BYTES:
            raise ValueError("种子文件过大，无法进入下载队列")
        return base64.b64encode(path.read_bytes()).decode("ascii")

    def _materialize_torrent(self, task: Task, payload: dict[str, Any]) -> str | None:
        raw = payload.get("torrent_b64")
        if not raw:
            return None
        folder = Path(settings.data_path) / "download_queue"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{task.id}.torrent"
        path.write_bytes(base64.b64decode(raw))
        return str(path)

    def _dedup_key(self, media_info: Any, downloader_id: str, user_id: int | None, torrent_b64: str) -> str:
        enclosure = str(getattr(media_info, "enclosure", "") or "")
        match = re.search(r"btih:([A-Za-z0-9]+)", enclosure)
        if match:
            resource = f"btih:{match.group(1).lower()}"
        elif torrent_b64:
            resource = f"torrent:{hashlib.sha256(torrent_b64.encode()).hexdigest()}"
        else:
            resource = "|".join(
                str(value or "")
                for value in (
                    getattr(media_info, "org_string", ""),
                    getattr(media_info, "size", ""),
                    getattr(media_info, "page_url", ""),
                )
            )
        identity = getattr(media_info, "identity_id", "") or (
            f"{getattr(media_info, 'anchor_provider', '')}:{getattr(media_info, 'anchor_external_id', '')}"
        )
        season_episode = (
            media_info.get_season_episode_string() if hasattr(media_info, "get_season_episode_string") else ""
        )
        raw = f"{downloader_id}|{user_id}|{identity}|{season_episode}|{resource}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _downloader_lock(self, downloader_id: str) -> threading.Lock:
        with self._guard:
            lock = self._locks.get(downloader_id)
            if lock is None:
                lock = threading.Lock()
                self._locks[downloader_id] = lock
            return lock

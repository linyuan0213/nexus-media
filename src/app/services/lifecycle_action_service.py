"""媒体流转详情页的人工操作：重试、取消、手动识别。"""

from __future__ import annotations

import uuid
from typing import Any

import log
from app.db.repositories.lifecycle_repository import LifecycleRepository, lifecycle_event_to_dict
from app.domain.lifecycle import LifecycleStage, LifecycleStatus
from app.infrastructure.task_queue import create_task_queue
from app.services.lifecycle_service import LifecycleProjector


class LifecycleActionError(Exception):
    """人工操作无法执行时抛出，由 API 返回可读错误。"""


class LifecycleActionService:
    def __init__(
        self,
        repo: LifecycleRepository | None = None,
        projector: LifecycleProjector | None = None,
        downloader: Any | None = None,
    ):
        self._repo = repo or LifecycleRepository()
        self._projector = projector or LifecycleProjector(self._repo)
        self._downloader = downloader

    def _state(self, identity_id: str, season: int, episode: int) -> tuple[str, str]:
        current = self._repo.get_current(identity_id, season=season, episode=episode)
        if current is None:
            current = self._repo.get_grouped_identity(identity_id)
        if current is None:
            raise LifecycleActionError("找不到该分集的流转记录")
        if isinstance(current, dict):
            return str(current.get("STAGE") or ""), str(current.get("STATUS") or "")
        return str(current.STAGE or ""), str(current.STATUS or "")

    def retry(self, identity_id: str, season: int = 0, episode: int = 0) -> dict[str, Any]:
        _, status = self._state(identity_id, season, episode)
        if status not in {
            LifecycleStatus.FAILED.value,
            LifecycleStatus.DEAD.value,
            LifecycleStatus.BLOCKED.value,
        }:
            raise LifecycleActionError("当前状态不需要重试")
        latest = self._latest_event(identity_id, season, episode)
        payload = self._payload(latest)
        queue_name = str(payload.get("queue") or "")
        task_id = str(payload.get("task_id") or "")
        if not queue_name or not task_id:
            raise LifecycleActionError("当前条目没有可重试的队列任务，请使用手动识别或重新搜索")
        queue = create_task_queue(queue_name)
        try:
            task = queue.get(task_id)
            if task is None:
                raise LifecycleActionError("原任务已结束或不存在，无法重试")
            new_task = queue.enqueue(
                task.task_type,
                task.payload,
                dedup_key=f"manual-retry:{uuid.uuid4().hex}",
                priority=task.priority,
                max_attempts=task.max_attempts,
            )
        finally:
            queue.close()
        current = self._repo.get_current(identity_id, season=season, episode=episode)
        if current is not None and str(current.STAGE or "").startswith("download"):
            task = self._repo.latest_download_task(identity_id)
            if task is not None and self._downloader is not None:
                downloader_id, download_id = task
                self._downloader.delete_torrents(downloader_id=downloader_id, delete_file=True, ids=[download_id])
        if current is not None:
            self._projector.record(
                identity_id=identity_id,
                stage=str(current.STAGE),
                status=LifecycleStatus.QUEUED,
                event_type="lifecycle.retry.requested",
                media_type=str(current.MEDIA_TYPE or "movie"),
                season=int(current.SEASON or 0),
                episode=int(current.EPISODE or 0),
                run_id=new_task.id,
                trace_id=str(current.TRACE_ID or ""),
                title=current.TITLE,
                year=current.YEAR,
                poster=current.POSTER,
                source_provider=current.SOURCE_PROVIDER,
                content_profile=current.CONTENT_PROFILE,
                user_id=current.USER_ID,
                message="手动重新提交任务",
                payload={"queue": queue_name, "task_id": new_task.id, "source_task_id": task_id},
                event_key=f"manual-retry:{new_task.id}",
            )
        log.info(f"[LifecycleAction]重试 identity={identity_id} task={new_task.id}")
        return {"action": "retry", "task_id": new_task.id, "queue": queue_name}

    def pause(self, identity_id: str, season: int = 0, episode: int = 0) -> dict[str, Any]:
        stage, status = self._state(identity_id, season, episode)
        if stage != LifecycleStage.DOWNLOADING.value or status not in {
            LifecycleStatus.QUEUED.value,
            LifecycleStatus.RUNNING.value,
            LifecycleStatus.RETRYING.value,
        }:
            raise LifecycleActionError("只有下载中的任务可以暂停")
        task = self._repo.latest_download_task(identity_id)
        if task is None or self._downloader is None:
            raise LifecycleActionError("没有找到可暂停的下载任务")
        downloader_id, download_id = task
        self._downloader.stop_torrents(downloader_id, [download_id])
        self._record_state(identity_id, season, episode, LifecycleStatus.PAUSED, "lifecycle.paused", "下载已暂停")
        return {"action": "pause", "download_id": download_id}

    def resume(self, identity_id: str, season: int = 0, episode: int = 0) -> dict[str, Any]:
        stage, status = self._state(identity_id, season, episode)
        if stage != LifecycleStage.DOWNLOADING.value or status != LifecycleStatus.PAUSED.value:
            raise LifecycleActionError("只有已暂停的下载可以继续")
        task = self._repo.latest_download_task(identity_id)
        if task is None or self._downloader is None:
            raise LifecycleActionError("没有找到可继续的下载任务")
        downloader_id, download_id = task
        self._downloader.start_torrents(downloader_id, [download_id])
        self._record_state(identity_id, season, episode, LifecycleStatus.RUNNING, "lifecycle.resumed", "下载已继续")
        return {"action": "resume", "download_id": download_id}

    def cancel(self, identity_id: str, season: int = 0, episode: int = 0) -> dict[str, Any]:
        stage, status = self._state(identity_id, season, episode)
        if status in {
            LifecycleStatus.SUCCEEDED.value,
            LifecycleStatus.CANCELLED.value,
        } or stage in {
            LifecycleStage.IN_LIBRARY.value,
            LifecycleStage.SCRAPED.value,
            LifecycleStage.TRANSFERRED.value,
        }:
            raise LifecycleActionError("已完成或已入库的任务不能取消")
        latest = self._latest_event(identity_id, season, episode)
        payload = self._payload(latest)
        queue_name = str(payload.get("queue") or "")
        task_id = str(payload.get("task_id") or "")
        cancelled_task = False
        if queue_name and task_id:
            queue = create_task_queue(queue_name)
            try:
                task = queue.get(task_id)
                if task is not None:
                    cancelled_task = bool(queue.cancel(task))
            finally:
                queue.close()
        current = self._repo.get_current(identity_id, season=season, episode=episode)
        if current is not None:
            self._projector.record(
                identity_id=identity_id,
                stage=str(current.STAGE),
                status=LifecycleStatus.CANCELLED,
                event_type="lifecycle.cancelled",
                media_type=str(current.MEDIA_TYPE or "movie"),
                season=int(current.SEASON or 0),
                episode=int(current.EPISODE or 0),
                run_id=str(current.RUN_ID or ""),
                trace_id=str(current.TRACE_ID or ""),
                title=current.TITLE,
                year=current.YEAR,
                poster=current.POSTER,
                source_provider=current.SOURCE_PROVIDER,
                content_profile=current.CONTENT_PROFILE,
                user_id=current.USER_ID,
                message="人工取消任务",
                payload={"queue": queue_name, "task_id": task_id},
                event_key=f"lifecycle-cancel:{identity_id}:{season}:{episode}:{uuid.uuid4().hex}",
            )
        log.info(f"[LifecycleAction]取消 identity={identity_id} task={task_id} queue={queue_name}")
        return {"action": "cancel", "task_id": task_id, "queue_cancelled": cancelled_task}

    def identify(
        self,
        identity_id: str,
        *,
        provider: str,
        external_id: str,
        title: str | None = None,
        year: str | None = None,
        poster: str | None = None,
        season: int = 0,
        episode: int = 0,
    ) -> dict[str, Any]:
        if not provider or not external_id:
            raise LifecycleActionError("provider 和 external_id 不能为空")
        current = self._repo.get_current(identity_id, season=season, episode=episode)
        if current is None:
            current = self._repo.get_grouped_identity(identity_id)
        if current is not None:
            if isinstance(current, dict):
                current_season = int(current.get("SEASON") or 0)
                current_episode = int(current.get("EPISODE") or 0)
            else:
                current_season = int(current.SEASON or 0)
                current_episode = int(current.EPISODE or 0)
            if not season:
                season = current_season
            if not episode:
                episode = current_episode
        updated = self._repo.update_metadata(
            identity_id,
            title=title,
            year=year,
            poster=poster,
            source_provider=provider,
            season=season,
            episode=episode,
        )
        self._projector.record(
            identity_id=identity_id,
            stage=LifecycleStage.IDENTIFIED,
            status=LifecycleStatus.SUCCEEDED,
            event_type="manual.identified",
            media_type="movie",
            season=season,
            episode=episode,
            title=title,
            year=year,
            poster=poster,
            source_provider=provider,
            message=f"手动识别为 {provider}:{external_id}",
            payload={"provider": provider, "external_id": external_id},
            event_key=f"manual-identify:{identity_id}:{season}:{episode}:{provider}:{external_id}",
        )
        log.info(f"[LifecycleAction]手动识别 identity={identity_id} ref={provider}:{external_id}")
        return {"action": "identify", "updated": updated, "provider": provider, "external_id": external_id}

    def _record_state(
        self,
        identity_id: str,
        season: int,
        episode: int,
        status: LifecycleStatus,
        event_type: str,
        message: str,
    ) -> None:
        current = self._repo.get_current(identity_id, season=season, episode=episode)
        if current is None:
            current = self._repo.get_grouped_identity(identity_id)
        if current is None:
            return
        if isinstance(current, dict):
            data = current
        else:
            data = {
                "STAGE": current.STAGE,
                "MEDIA_TYPE": current.MEDIA_TYPE,
                "SEASON": current.SEASON,
                "EPISODE": current.EPISODE,
                "RUN_ID": current.RUN_ID,
                "TRACE_ID": current.TRACE_ID,
                "TITLE": current.TITLE,
                "YEAR": current.YEAR,
                "POSTER": current.POSTER,
                "SOURCE_PROVIDER": current.SOURCE_PROVIDER,
                "CONTENT_PROFILE": current.CONTENT_PROFILE,
                "USER_ID": current.USER_ID,
            }
        self._projector.record(
            identity_id=identity_id,
            stage=str(data.get("STAGE") or LifecycleStage.DOWNLOADING.value),
            status=status,
            event_type=event_type,
            media_type=str(data.get("MEDIA_TYPE") or "movie"),
            season=int(data.get("SEASON") or season or 0),
            episode=int(data.get("EPISODE") or episode or 0),
            run_id=str(data.get("RUN_ID") or ""),
            trace_id=str(data.get("TRACE_ID") or ""),
            title=data.get("TITLE"),
            year=data.get("YEAR"),
            poster=data.get("POSTER"),
            source_provider=data.get("SOURCE_PROVIDER"),
            content_profile=data.get("CONTENT_PROFILE"),
            user_id=data.get("USER_ID"),
            message=message,
            event_key=f"{event_type}:{identity_id}:{uuid.uuid4().hex}",
        )

    def _latest_event(self, identity_id: str, season: int, episode: int):
        latest = self._repo.latest_event(identity_id, season=season, episode=episode)
        if latest is None and (season or episode):
            latest = self._repo.latest_event(identity_id)
        return latest

    @staticmethod
    def _payload(event) -> dict[str, Any]:
        if event is None:
            return {}
        raw = lifecycle_event_to_dict(event).get("PAYLOAD")
        return raw if isinstance(raw, dict) else {}

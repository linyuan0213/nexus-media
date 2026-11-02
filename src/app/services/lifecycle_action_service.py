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
    def __init__(self, repo: LifecycleRepository | None = None, projector: LifecycleProjector | None = None):
        self._repo = repo or LifecycleRepository()
        self._projector = projector or LifecycleProjector(self._repo)

    def retry(self, identity_id: str, season: int = 0, episode: int = 0) -> dict[str, Any]:
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

    def cancel(self, identity_id: str, season: int = 0, episode: int = 0) -> dict[str, Any]:
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

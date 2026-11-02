"""媒体生命周期投影服务（ADR-026）."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

import log
from app.db.models.lifecycle import MediaLifecycleEvent
from app.db.repositories.lifecycle_repository import LifecycleRepository
from app.domain.lifecycle import LifecycleStage, LifecycleStatus, map_task_status


class LifecycleProjector:
    """唯一写入生命周期读模型的服务.

    只做投影，不驱动下载/转移/刮削业务。
    """

    def __init__(self, repository: LifecycleRepository | None = None):
        self._repo = repository or LifecycleRepository()

    def record(
        self,
        *,
        identity_id: str,
        stage: LifecycleStage | str,
        status: LifecycleStatus | str,
        event_type: str,
        media_type: str = "movie",
        season: int = 0,
        episode: int = 0,
        run_id: str | None = None,
        trace_id: str | None = None,
        title: str | None = None,
        year: str | None = None,
        poster: str | None = None,
        progress: int | None = None,
        source_provider: str | None = None,
        content_profile: str | None = None,
        user_id: int | None = None,
        retry_count: int = 0,
        next_retry_at: datetime | None = None,
        error: str | None = None,
        message: str | None = None,
        payload: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
        event_key: str | None = None,
    ) -> bool:
        if not identity_id:
            raise ValueError("identity_id is required")
        occurred = occurred_at or datetime.now()
        stage_value = LifecycleStage(stage).value
        status_value = LifecycleStatus(status).value
        key = event_key or self._event_key(
            identity_id, season, episode, stage_value, event_type, trace_id, occurred
        )
        event = MediaLifecycleEvent(
            EVENT_KEY=key,
            IDENTITY_ID=identity_id,
            MEDIA_TYPE=media_type or "movie",
            SEASON=int(season or 0),
            EPISODE=int(episode or 0),
            RUN_ID=run_id,
            TRACE_ID=trace_id,
            STAGE=stage_value,
            EVENT_TYPE=event_type,
            STATUS=status_value,
            MESSAGE=(message or "")[:512] or None,
            PAYLOAD=self._repo.event_payload(payload),
            USER_ID=user_id,
            OCCURRED_AT=occurred,
            CREATED_AT=datetime.now(),
        )
        snapshot = {
            "IDENTITY_ID": identity_id,
            "MEDIA_TYPE": media_type or "movie",
            "SEASON": int(season or 0),
            "EPISODE": int(episode or 0),
            "TITLE": title,
            "YEAR": year,
            "POSTER": poster,
            "STAGE": stage_value,
            "STATUS": status_value,
            "RUN_ID": run_id,
            "TRACE_ID": trace_id,
            "SOURCE_PROVIDER": source_provider,
            "CONTENT_PROFILE": content_profile,
            "USER_ID": user_id,
            "STAGE_STARTED_AT": occurred,
            "LAST_EVENT_AT": occurred,
            "NEXT_RETRY_AT": next_retry_at,
            "RETRY_COUNT": max(0, int(retry_count or 0)),
            "LAST_ERROR": error,
            "CREATED_AT": datetime.now(),
            "UPDATED_AT": datetime.now(),
        }
        if progress is not None:
            snapshot["PROGRESS"] = max(0, min(100, int(progress)))
        try:
            created = self._repo.record_event(event, snapshot)
            if created:
                log.debug(
                    f"[Lifecycle]记录事件 {event_type} identity={identity_id} "
                    f"stage={stage_value} status={status_value}"
                )
            return created
        except Exception as exc:  # noqa: BLE001 - 生命周期失败不影响业务
            log.warn(f"[Lifecycle]写入生命周期事件失败: {exc}")
            return False

    def record_task(
        self,
        task: Any,
        *,
        stage: LifecycleStage | str,
        event_type: str,
        identity_id: str | None = None,
        season: int = 0,
        episode: int = 0,
        **kwargs: Any,
    ) -> bool:
        payload = getattr(task, "payload", {}) or {}
        status = map_task_status(getattr(task, "status", None))
        return self.record(
            identity_id=identity_id or str(payload.get("identity_id") or ""),
            stage=stage,
            status=status,
            event_type=event_type,
            season=season,
            episode=episode,
            run_id=payload.get("run_id"),
            trace_id=payload.get("trace_id"),
            source_provider=payload.get("source_provider") or payload.get("provider"),
            content_profile=payload.get("content_profile"),
            user_id=payload.get("user_id"),
            retry_count=getattr(task, "attempts", 0),
            error=getattr(task, "last_error", None),
            payload={"task_id": getattr(task, "id", None), "queue": getattr(task, "queue_name", None)},
            **kwargs,
        )

    @staticmethod
    def _event_key(
        identity_id: str,
        season: int,
        episode: int,
        stage: str,
        event_type: str,
        trace_id: str | None,
        occurred: datetime,
    ) -> str:
        raw = f"{identity_id}|{season}|{episode}|{stage}|{event_type}|{trace_id or ''}|{occurred.isoformat()}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

"""媒体生命周期读模型仓储（ADR-026）."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func

import log
from app.db.models.lifecycle import MediaLifecycle, MediaLifecycleEvent
from app.db.repositories.base_repository import BaseRepository
from app.db.repositories.data_scope import apply_owner_scope
from app.utils.json_utils import JsonUtils


class LifecycleRepository(BaseRepository):
    """生命周期当前状态与事件时间线仓储."""

    def record_event(self, event: MediaLifecycleEvent, snapshot: dict[str, Any]) -> bool:
        """幂等写入事件并更新当前快照；EVENT_KEY 已存在时返回 False."""
        with self.session() as db:
            exists = (
                db.query(MediaLifecycleEvent.ID)
                .filter(MediaLifecycleEvent.EVENT_KEY == event.EVENT_KEY)
                .first()
            )
            if exists is not None:
                return False
            db.add(event)
            current = (
                db.query(MediaLifecycle)
                .filter(
                    MediaLifecycle.IDENTITY_ID == event.IDENTITY_ID,
                    MediaLifecycle.SEASON == event.SEASON,
                    MediaLifecycle.EPISODE == event.EPISODE,
                )
                .first()
            )
            if current is None:
                current = MediaLifecycle(**snapshot)
                db.add(current)
            elif event.OCCURRED_AT >= (current.LAST_EVENT_AT or event.OCCURRED_AT):
                stage_changed = current.STAGE != event.STAGE
                for key, value in snapshot.items():
                    if key in {"IDENTITY_ID", "SEASON", "EPISODE", "CREATED_AT", "STAGE_STARTED_AT"}:
                        continue
                    if key in {"TITLE", "YEAR", "POSTER", "USER_ID"} and value in {None, ""}:
                        continue
                    setattr(current, key, value)
                if stage_changed:
                    current.STAGE_STARTED_AT = event.OCCURRED_AT
            db.commit()
            return True

    def get_current(
        self, identity_id: str, season: int = 0, episode: int = 0, *, user=None
    ) -> MediaLifecycle | None:
        with self.readonly() as db:
            query = db.query(MediaLifecycle).filter(
                MediaLifecycle.IDENTITY_ID == identity_id,
                MediaLifecycle.SEASON == season,
                MediaLifecycle.EPISODE == episode,
            )
            if user is not None:
                query = apply_owner_scope(query, MediaLifecycle, user, include_shared=False)
            return query.first()

    def list_current(
        self,
        *,
        stage: str | None = None,
        status: str | None = None,
        media_type: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        pagenum: int = 20,
        user=None,
    ) -> tuple[list[MediaLifecycle], int]:
        with self.readonly() as db:
            query = db.query(MediaLifecycle)
            if user is not None:
                query = apply_owner_scope(query, MediaLifecycle, user, include_shared=False)
            if stage:
                query = query.filter(MediaLifecycle.STAGE == stage)
            if status:
                query = query.filter(MediaLifecycle.STATUS == status)
            if media_type:
                query = query.filter(MediaLifecycle.MEDIA_TYPE == media_type)
            if keyword:
                query = query.filter(MediaLifecycle.TITLE.ilike(f"%{keyword}%"))
            total = query.with_entities(func.count(MediaLifecycle.ID)).scalar() or 0
            rows = (
                query.order_by(MediaLifecycle.LAST_EVENT_AT.desc(), MediaLifecycle.ID.desc())
                .offset((max(1, page) - 1) * max(1, pagenum))
                .limit(max(1, pagenum))
                .all()
            )
            return rows, int(total)

    def list_events(
        self, identity_id: str, season: int = 0, episode: int = 0, limit: int = 200, *, user=None
    ) -> list[MediaLifecycleEvent]:
        with self.readonly() as db:
            query = db.query(MediaLifecycleEvent).filter(
                MediaLifecycleEvent.IDENTITY_ID == identity_id,
                MediaLifecycleEvent.SEASON == season,
                MediaLifecycleEvent.EPISODE == episode,
            )
            if user is not None:
                query = apply_owner_scope(query, MediaLifecycleEvent, user, include_shared=False)
            return (
                query.order_by(MediaLifecycleEvent.OCCURRED_AT.asc(), MediaLifecycleEvent.ID.asc())
                .limit(max(1, min(1000, int(limit))))
                .all()
            )

    @staticmethod
    def event_payload(value: Any) -> str:
        return JsonUtils.dumps(JsonUtils.to_jsonable(value or {}))


def lifecycle_row_to_dict(row: MediaLifecycle) -> dict[str, Any]:
    data = row.as_dict()
    for key in ("STAGE_STARTED_AT", "LAST_EVENT_AT", "NEXT_RETRY_AT", "CREATED_AT", "UPDATED_AT"):
        value = data.get(key)
        if isinstance(value, datetime):
            data[key] = value.isoformat()
    return data


def lifecycle_event_to_dict(row: MediaLifecycleEvent) -> dict[str, Any]:
    data = row.as_dict()
    for key in ("OCCURRED_AT", "CREATED_AT"):
        value = data.get(key)
        if isinstance(value, datetime):
            data[key] = value.isoformat()
    raw_payload = data.get("PAYLOAD")
    if isinstance(raw_payload, str) and raw_payload:
        try:
            data["PAYLOAD"] = JsonUtils.loads(raw_payload)
        except Exception as exc:  # noqa: BLE001
            log.debug(f"[Lifecycle]解析事件 payload 失败: {exc}")
    return data

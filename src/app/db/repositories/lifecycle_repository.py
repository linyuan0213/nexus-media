"""媒体生命周期读模型仓储（ADR-026）."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func

import log
from app.db.models.lifecycle import MediaLifecycle, MediaLifecycleEvent
from app.db.repositories.base_repository import BaseRepository
from app.db.repositories.data_scope import apply_owner_scope
from app.domain.lifecycle import LifecycleStage, LifecycleStatus, stage_rank
from app.utils.json_utils import JsonUtils


class LifecycleRepository(BaseRepository):
    """生命周期当前状态与事件时间线仓储."""

    def record_event(
        self, event: MediaLifecycleEvent, snapshot: dict[str, Any], *, update_snapshot: bool = True
    ) -> bool:
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
            if not update_snapshot:
                db.commit()
                return True
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

    def list_identity_rows(self, identity_id: str, *, user=None) -> list[MediaLifecycle]:
        with self.readonly() as db:
            query = db.query(MediaLifecycle).filter(MediaLifecycle.IDENTITY_ID == identity_id)
            if user is not None:
                query = apply_owner_scope(query, MediaLifecycle, user, include_shared=False)
            return query.order_by(MediaLifecycle.SEASON.asc(), MediaLifecycle.EPISODE.asc()).all()

    def stats_current(self, *, user=None) -> dict[str, Any]:
        with self.readonly() as db:
            base = db.query(MediaLifecycle)
            if user is not None:
                base = apply_owner_scope(base, MediaLifecycle, user, include_shared=False)
            status_rows = (
                base.with_entities(MediaLifecycle.STATUS, func.count(MediaLifecycle.ID))
                .group_by(MediaLifecycle.STATUS)
                .all()
            )
            stage_rows = (
                base.with_entities(MediaLifecycle.STAGE, func.count(MediaLifecycle.ID))
                .group_by(MediaLifecycle.STAGE)
                .all()
            )
            return {
                "total": sum(int(count) for _, count in status_rows),
                "by_status": {str(key): int(count) for key, count in status_rows},
                "by_stage": {str(key): int(count) for key, count in stage_rows},
            }

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

    def list_grouped(
        self,
        *,
        stage: str | None = None,
        status: str | None = None,
        media_type: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        pagenum: int = 20,
        user=None,
    ) -> tuple[list[dict[str, Any]], int]:
        with self.readonly() as db:
            query = db.query(MediaLifecycle)
            if user is not None:
                query = apply_owner_scope(query, MediaLifecycle, user, include_shared=False)
            if media_type:
                query = query.filter(MediaLifecycle.MEDIA_TYPE == media_type)
            if keyword:
                query = query.filter(MediaLifecycle.TITLE.ilike(f"%{keyword}%"))
            rows = query.order_by(MediaLifecycle.LAST_EVENT_AT.desc(), MediaLifecycle.ID.desc()).all()
        grouped = _group_lifecycle_rows(rows)
        if stage:
            grouped = [item for item in grouped if item["STAGE"] == stage]
        if status:
            grouped = [item for item in grouped if item["STATUS"] == status]
        total = len(grouped)
        start = (max(1, page) - 1) * max(1, pagenum)
        return grouped[start : start + max(1, pagenum)], total

    def stats_grouped(self, *, user=None) -> dict[str, Any]:
        with self.readonly() as db:
            query = db.query(MediaLifecycle)
            if user is not None:
                query = apply_owner_scope(query, MediaLifecycle, user, include_shared=False)
            grouped = _group_lifecycle_rows(query.all())
        by_status: dict[str, int] = {}
        by_stage: dict[str, int] = {}
        for item in grouped:
            by_status[item["STATUS"]] = by_status.get(item["STATUS"], 0) + 1
            by_stage[item["STAGE"]] = by_stage.get(item["STAGE"], 0) + 1
        return {"total": len(grouped), "by_status": by_status, "by_stage": by_stage}

    @staticmethod
    def event_payload(value: Any) -> str:
        return JsonUtils.dumps(JsonUtils.to_jsonable(value or {}))


def _group_lifecycle_rows(rows: list[MediaLifecycle]) -> list[dict[str, Any]]:
    groups: dict[str, list[MediaLifecycle]] = {}
    for row in rows:
        groups.setdefault(str(row.IDENTITY_ID), []).append(row)
    result: list[dict[str, Any]] = []
    status_priority = {
        LifecycleStatus.SUCCEEDED.value: 0,
        LifecycleStatus.CANCELLED.value: 1,
        LifecycleStatus.QUEUED.value: 2,
        LifecycleStatus.RETRYING.value: 3,
        LifecycleStatus.RUNNING.value: 4,
        LifecycleStatus.BLOCKED.value: 5,
        LifecycleStatus.FAILED.value: 6,
        LifecycleStatus.DEAD.value: 7,
    }
    for items in groups.values():
        representative = max(items, key=lambda item: item.LAST_EVENT_AT or item.UPDATED_AT)
        stage = min(items, key=lambda item: stage_rank(item.STAGE)).STAGE
        status = max(items, key=lambda item: status_priority.get(item.STATUS, 0)).STATUS
        completed = sum(
            1
            for item in items
            if item.STAGE in {LifecycleStage.SCRAPED.value, LifecycleStage.IN_LIBRARY.value}
            and item.STATUS == LifecycleStatus.SUCCEEDED.value
        )
        in_library = sum(1 for item in items if item.STAGE == LifecycleStage.IN_LIBRARY.value)
        data = representative.as_dict()
        if status == LifecycleStatus.SUCCEEDED.value and stage not in {
            LifecycleStage.SCRAPED.value,
            LifecycleStage.IN_LIBRARY.value,
        }:
            status = LifecycleStatus.RUNNING.value
        data["STAGE"] = stage
        data["STATUS"] = status
        data["STAGE_STARTED_AT"] = max(
            (item.STAGE_STARTED_AT for item in items),
            default=representative.STAGE_STARTED_AT,
        )
        data["LAST_EVENT_AT"] = max(
            (item.LAST_EVENT_AT for item in items),
            default=representative.LAST_EVENT_AT,
        )
        data["PROGRESS"] = int(completed * 100 / len(items)) if items else 0
        data["EPISODE_COUNT"] = len(items)
        data["COMPLETED_EPISODES"] = completed
        data["IN_LIBRARY_EPISODES"] = in_library
        result.append(data)
    result.sort(key=lambda item: item.get("LAST_EVENT_AT") or datetime.min, reverse=True)
    return result


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

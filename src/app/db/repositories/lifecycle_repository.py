"""媒体生命周期读模型仓储（ADR-026）."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func

import log
from app.db.models.lifecycle import MediaLifecycle, MediaLifecycleEvent
from app.db.models.subscribe import SubscribeTvs
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
            exists = db.query(MediaLifecycleEvent.ID).filter(MediaLifecycleEvent.EVENT_KEY == event.EVENT_KEY).first()
            if exists is not None:
                if update_snapshot:
                    self._apply_snapshot(db, event, snapshot)
                db.commit()
                return False
            db.add(event)
            if not update_snapshot:
                db.commit()
                return True
            self._apply_snapshot(db, event, snapshot)
            db.commit()
            return True

    def _apply_snapshot(self, db, event: MediaLifecycleEvent, snapshot: dict[str, Any]) -> None:
        """按阶段单调推进快照；旧阶段事件只保留在时间线，不回退当前状态。"""
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
            db.add(MediaLifecycle(**snapshot))
            return
        current_rank = stage_rank(current.STAGE)
        event_rank = stage_rank(event.STAGE)
        advanced = event_rank > current_rank
        regressed = event_rank < current_rank
        if not advanced and event.OCCURRED_AT < (current.LAST_EVENT_AT or event.OCCURRED_AT):
            return
        skip_keys = {"IDENTITY_ID", "SEASON", "EPISODE", "CREATED_AT", "STAGE_STARTED_AT"}
        if regressed:
            skip_keys |= {
                "STAGE",
                "STATUS",
                "PROGRESS",
                "RUN_ID",
                "TRACE_ID",
                "LAST_ERROR",
                "NEXT_RETRY_AT",
                "RETRY_COUNT",
            }
        for key, value in snapshot.items():
            if key in skip_keys:
                continue
            if key in {"TITLE", "YEAR", "POSTER", "USER_ID"} and value in {None, ""}:
                continue
            if key == "LAST_EVENT_AT" and advanced:
                value = max(value, current.LAST_EVENT_AT or value)
            setattr(current, key, value)
        if advanced:
            current.STAGE_STARTED_AT = event.OCCURRED_AT

    def get_current(self, identity_id: str, season: int = 0, episode: int = 0, *, user=None) -> MediaLifecycle | None:
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
            rows = (
                query.order_by(MediaLifecycleEvent.OCCURRED_AT.asc(), MediaLifecycleEvent.ID.asc())
                .limit(max(1, min(1000, int(limit))))
                .all()
            )
            # 生命周期页面按阶段顺序展示；同一阶段内再按发生时间排序。
            return sorted(
                rows,
                key=lambda event: (
                    stage_rank(event.STAGE) if stage_rank(event.STAGE) >= 0 else 999,
                    event.OCCURRED_AT,
                    event.ID,
                ),
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
            query = db.query(MediaLifecycle).filter(MediaLifecycle.IDENTITY_ID != "preview")
            if user is not None:
                query = apply_owner_scope(query, MediaLifecycle, user, include_shared=False)
            if media_type:
                query = query.filter(MediaLifecycle.MEDIA_TYPE == media_type)
            if keyword:
                query = query.filter(MediaLifecycle.TITLE.ilike(f"%{keyword}%"))
            rows = query.order_by(MediaLifecycle.LAST_EVENT_AT.desc(), MediaLifecycle.ID.desc()).all()
            identities = list({str(row.IDENTITY_ID) for row in rows})
            activity: dict[str, datetime] = {}
            if identities:
                events = (
                    db.query(
                        MediaLifecycleEvent.IDENTITY_ID,
                        MediaLifecycleEvent.OCCURRED_AT,
                        MediaLifecycleEvent.EVENT_TYPE,
                    )
                    .filter(MediaLifecycleEvent.IDENTITY_ID.in_(identities))
                    .all()
                )
                for identity, occurred, event_type in events:
                    # 入库回填/今天重扫 NFO 的时间不代表真实入库顺序
                    if (
                        event_type
                        in {
                            "reconcile.library.present",
                            "reconcile.scrape.completed",
                        }
                        or occurred is None
                    ):
                        continue
                    key = str(identity)
                    if key not in activity or occurred > activity[key]:
                        activity[key] = occurred
            subscription_map = _subscription_map(db, identities)
        grouped = _group_lifecycle_rows(rows)
        for item in grouped:
            item["ACTIVITY_AT"] = activity.get(str(item.get("IDENTITY_ID")), datetime.min)
        _apply_subscription_state(grouped, subscription_map)
        grouped.sort(
            key=lambda item: (item.get("ACTIVITY_AT") or datetime.min, item.get("ID") or 0),
            reverse=True,
        )
        if stage:
            grouped = [item for item in grouped if item["STAGE"] == stage]
        if status:
            grouped = [item for item in grouped if item["STATUS"] == status]
        total = len(grouped)
        start = (max(1, page) - 1) * max(1, pagenum)
        return grouped[start : start + max(1, pagenum)], total

    def get_grouped_identity(self, identity_id: str, *, user=None) -> dict[str, Any] | None:
        """按作品聚合单集记录，并叠加订阅总集数。"""
        with self.readonly() as db:
            query = db.query(MediaLifecycle).filter(MediaLifecycle.IDENTITY_ID == identity_id)
            if user is not None:
                query = apply_owner_scope(query, MediaLifecycle, user, include_shared=False)
            rows = query.all()
            grouped = _group_lifecycle_rows(rows)
            if not grouped:
                return None
            _apply_subscription_state(grouped, _subscription_map(db, [identity_id]))
            return grouped[0]

    def list_subscription_summaries(self, identity_id: str, *, user=None) -> list[dict[str, Any]]:
        """读取订阅侧总集数，用于补齐尚未进入生命周期记录的分集。"""
        with self.readonly() as db:
            query = db.query(SubscribeTvs).filter(SubscribeTvs.IDENTITY_ID == identity_id)
            if user is not None:
                query = apply_owner_scope(query, SubscribeTvs, user, include_shared=False)
            rows = query.order_by(SubscribeTvs.SEASON.asc()).all()
            return [
                {
                    "season": row.SEASON,
                    "total_ep": int(row.TOTAL_EP or 0),
                    "current_ep": int(row.CURRENT_EP or 0),
                    "state": row.STATE,
                    "name": row.NAME,
                }
                for row in rows
            ]

    def stats_grouped(self, *, user=None) -> dict[str, Any]:
        with self.readonly() as db:
            query = db.query(MediaLifecycle).filter(MediaLifecycle.IDENTITY_ID != "preview")
            if user is not None:
                query = apply_owner_scope(query, MediaLifecycle, user, include_shared=False)
            rows = query.all()
            identities = list({str(row.IDENTITY_ID) for row in rows})
            grouped = _group_lifecycle_rows(rows)
            _apply_subscription_state(grouped, _subscription_map(db, identities))
        by_status: dict[str, int] = {}
        by_stage: dict[str, int] = {}
        for item in grouped:
            by_status[item["STATUS"]] = by_status.get(item["STATUS"], 0) + 1
            by_stage[item["STAGE"]] = by_stage.get(item["STAGE"], 0) + 1
        return {"total": len(grouped), "by_status": by_status, "by_stage": by_stage}

    @staticmethod
    def event_payload(value: Any) -> str:
        return JsonUtils.dumps(JsonUtils.to_jsonable(value or {}))


def _subscription_map(db, identities: list[str]) -> dict[str, tuple[int, str]]:
    if not identities:
        return {}
    subscriptions = (
        db.query(SubscribeTvs.IDENTITY_ID, SubscribeTvs.TOTAL_EP, SubscribeTvs.STATE)
        .filter(SubscribeTvs.IDENTITY_ID.in_(identities))
        .all()
    )
    result: dict[str, tuple[int, str]] = {}
    for identity, total_ep, sub_state in subscriptions:
        if not identity:
            continue
        key = str(identity)
        total_value = int(total_ep or 0)
        previous = result.get(key)
        if previous is None or total_value > previous[0]:
            result[key] = (total_value, str(sub_state or ""))
    return result


def _apply_subscription_state(grouped: list[dict[str, Any]], subscription_map: dict[str, tuple[int, str]]) -> None:
    """用订阅总集数约束整季状态，避免只统计已产生生命周期记录的分集。"""
    for item in grouped:
        sub = subscription_map.get(str(item.get("IDENTITY_ID")))
        if not sub:
            continue
        total_ep, sub_state = sub
        completed = int(item.get("COMPLETED_EPISODES") or 0)
        if total_ep > 0:
            item["EPISODE_COUNT"] = max(int(item.get("EPISODE_COUNT") or 0), total_ep)
            completed = min(total_ep, completed)
            item["COMPLETED_EPISODES"] = completed
            item["PROGRESS"] = round(completed * 100 / total_ep)
        if sub_state in {"D", "S", "R"}:
            # 仍在订阅中：即使现有分集全部入库，也不能标记为整部作品完成。
            if total_ep > 0 and completed < total_ep:
                item["STAGE"] = "downloading" if completed else "download_queued"
            else:
                item["STAGE"] = "subscribed"
            item["STATUS"] = "queued" if sub_state == "D" else "running"
        elif sub_state == "E":
            item["STATUS"] = "failed"
        elif sub_state == "N":
            item["STATUS"] = "cancelled"


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
        episode_items = [item for item in items if int(item.EPISODE or 0) > 0]
        state_items = episode_items or items
        stage = max(state_items, key=lambda item: stage_rank(item.STAGE)).STAGE
        status = max(state_items, key=lambda item: status_priority.get(item.STATUS, 0)).STATUS
        in_library = sum(
            1
            for item in state_items
            if item.STAGE == LifecycleStage.IN_LIBRARY.value and item.STATUS == LifecycleStatus.SUCCEEDED.value
        )
        completed = in_library
        data = representative.as_dict()
        if status == LifecycleStatus.SUCCEEDED.value and stage not in {
            LifecycleStage.SCRAPED.value,
            LifecycleStage.IN_LIBRARY.value,
        }:
            status = LifecycleStatus.RUNNING.value
        if episode_items:
            data["SEASON"] = max(int(item.SEASON or 0) for item in episode_items)
            data["EPISODE"] = max(int(item.EPISODE or 0) for item in episode_items)
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
        data["PROGRESS"] = int(completed * 100 / len(state_items)) if state_items else 0
        data["EPISODE_COUNT"] = len(state_items)
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

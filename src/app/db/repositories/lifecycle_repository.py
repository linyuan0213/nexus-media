"""媒体生命周期读模型仓储（ADR-026）."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy import func

import log
from app.db.models.download import DOWNLOADHISTORY
from app.db.models.lifecycle import MediaLifecycle, MediaLifecycleEvent
from app.db.models.subscribe import SubscribeHistory, SubscribeMovies, SubscribeTvEpisodes, SubscribeTvs
from app.db.models.transfer import TRANSFERHISTORY
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
            exists = db.query(MediaLifecycleEvent).filter(MediaLifecycleEvent.EVENT_KEY == event.EVENT_KEY).first()
            if exists is not None:
                if update_snapshot:
                    # 重复事件必须按首次发生时间修复快照；否则重启后的旧事件
                    # 会被误判为新一轮流转，把已入库状态打回转移排队。
                    repair_snapshot = dict(snapshot)
                    repair_snapshot["LAST_EVENT_AT"] = exists.OCCURRED_AT
                    self._apply_snapshot(db, exists, repair_snapshot)
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
        # 已入库/已刮削/已转移后再次出现下载/搜索/转移排队事件，视为新一轮流转；
        # 否则阶段单调会永久掩盖重下/洗版活动。
        restart_events = {
            "download.queued",
            "download.started",
            "search.started",
            "transfer.queued",
            "transfer.started",
            "scrape.queued",
            "scrape.started",
            "reconcile.download.queued",
            "reconcile.download.downloading",
        }
        terminal_stages = {"in_library", "scraped", "transferred", "downloaded"}
        restart = (
            str(current.STAGE or "") in terminal_stages
            and str(event.EVENT_TYPE or "") in restart_events
            and event.OCCURRED_AT > (current.STAGE_STARTED_AT or event.OCCURRED_AT)
        )
        advanced = restart or event_rank > current_rank
        regressed = event_rank < current_rank and not restart
        if not advanced and event.OCCURRED_AT < (current.LAST_EVENT_AT or event.OCCURRED_AT):
            # 旧事件不回退状态，但可以用更具体的元数据来源修复 content_id 兜底。
            provider = str(snapshot.get("SOURCE_PROVIDER") or "")
            if provider not in {"", "content_id"} and current.SOURCE_PROVIDER in {
                None,
                "",
                "content_id",
            }:
                current.SOURCE_PROVIDER = provider
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
                "LAST_EVENT_AT",
            }
        for key, value in snapshot.items():
            if key in skip_keys:
                continue
            if key in {"TITLE", "YEAR", "POSTER", "USER_ID"} and value in {None, ""}:
                continue
            if (
                key == "SOURCE_PROVIDER"
                and value in {None, "", "content_id"}
                and current.SOURCE_PROVIDER not in {None, "", "content_id"}
            ):
                continue
            if key == "LAST_EVENT_AT" and advanced and not restart:
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
        self,
        identity_id: str,
        season: int = 0,
        episode: int = 0,
        limit: int = 200,
        *,
        user=None,
        until: datetime | None = None,
    ) -> list[MediaLifecycleEvent]:
        with self.readonly() as db:
            query = db.query(MediaLifecycleEvent).filter(
                MediaLifecycleEvent.IDENTITY_ID == identity_id,
                MediaLifecycleEvent.SEASON == season,
                MediaLifecycleEvent.EPISODE == episode,
            )
            if user is not None:
                query = apply_owner_scope(query, MediaLifecycleEvent, user, include_shared=False)
            if until is not None:
                # 只展示快照已采纳的事件；新一轮中被旧规则忽略的事件不混入当前时间线
                query = query.filter(MediaLifecycleEvent.OCCURRED_AT <= until)
            rows = (
                query.order_by(MediaLifecycleEvent.OCCURRED_AT.asc(), MediaLifecycleEvent.ID.asc())
                .limit(max(1, min(1000, int(limit))))
                .all()
            )
            # 时间线按真实发生时间展示，不按阶段重排。
            return sorted(rows, key=lambda event: (event.OCCURRED_AT, event.ID))

    def latest_event(
        self, identity_id: str, *, season: int | None = None, episode: int | None = None
    ) -> MediaLifecycleEvent | None:
        with self.readonly() as db:
            query = db.query(MediaLifecycleEvent).filter(MediaLifecycleEvent.IDENTITY_ID == identity_id)
            if season is not None:
                query = query.filter(MediaLifecycleEvent.SEASON == int(season))
            if episode is not None:
                query = query.filter(MediaLifecycleEvent.EPISODE == int(episode))
            return query.order_by(MediaLifecycleEvent.OCCURRED_AT.desc(), MediaLifecycleEvent.ID.desc()).first()

    def latest_download_task(self, identity_id: str) -> tuple[str, str] | None:
        with self.readonly() as db:
            row = (
                db.query(DOWNLOADHISTORY.DOWNLOADER, DOWNLOADHISTORY.DOWNLOAD_ID)
                .filter(
                    DOWNLOADHISTORY.IDENTITY_ID == identity_id,
                    DOWNLOADHISTORY.DOWNLOAD_ID.isnot(None),
                    DOWNLOADHISTORY.DOWNLOAD_ID != "",
                )
                .order_by(DOWNLOADHISTORY.ID.desc())
                .first()
            )
            if row and row[1]:
                return str(row[0] or ""), str(row[1])
        return None

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
            active_identities = _active_subscription_identities(db, identities)
            completed_identities = _completed_subscription_identities(db, identities)
            cancelled_identities = _cancelled_subscription_identities(db, identities)
            grouped = _group_lifecycle_rows(rows)
            for item in grouped:
                item["ACTIVITY_AT"] = activity.get(str(item.get("IDENTITY_ID")), datetime.min)
            _apply_subscription_state(
                grouped, subscription_map, active_identities, completed_identities, cancelled_identities
            )
            existing = {str(item.get("IDENTITY_ID") or "") for item in grouped}
            synthetic = _active_subscription_items(db, user, existing)
        if keyword:
            key = keyword.strip().lower()
            synthetic = [item for item in synthetic if key in str(item.get("TITLE") or "").lower()]
        grouped.extend(synthetic)
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

    def update_metadata(
        self,
        identity_id: str,
        *,
        title: str | None = None,
        year: str | None = None,
        poster: str | None = None,
        source_provider: str | None = None,
        season: int | None = None,
        episode: int | None = None,
    ) -> int:
        with self.session() as db:
            query = db.query(MediaLifecycle).filter(MediaLifecycle.IDENTITY_ID == identity_id)
            if season:
                query = query.filter(MediaLifecycle.SEASON == int(season))
            if episode:
                query = query.filter(MediaLifecycle.EPISODE == int(episode))
            changes = {}
            if title:
                changes[MediaLifecycle.TITLE] = title
            if year:
                changes[MediaLifecycle.YEAR] = year
            if poster:
                changes[MediaLifecycle.POSTER] = poster
            if source_provider:
                changes[MediaLifecycle.SOURCE_PROVIDER] = source_provider
            if not changes:
                return 0
            updated = query.update(changes, synchronize_session=False)
            db.commit()
            return int(updated or 0)

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
            _apply_subscription_state(
                grouped,
                _subscription_map(db, [identity_id]),
                _active_subscription_identities(db, [identity_id]),
                _completed_subscription_identities(db, [identity_id]),
                _cancelled_subscription_identities(db, [identity_id]),
            )
            return grouped[0]

    def resolve_identity_by_anchor(self, provider: str | None, external_id: str | None) -> str | None:
        """按 anchor 找到业务表里的稳定 identity，避免产生 provider:external 影子条目。"""
        provider = str(provider or "").strip()
        external_id = str(external_id or "").strip()
        if not provider or not external_id:
            return None
        with self.readonly() as db:
            transfer = (
                db.query(TRANSFERHISTORY.IDENTITY_ID)
                .filter(
                    TRANSFERHISTORY.ANCHOR_PROVIDER == provider,
                    TRANSFERHISTORY.ANCHOR_EXTERNAL_ID == external_id,
                    TRANSFERHISTORY.IDENTITY_ID.isnot(None),
                )
                .order_by(TRANSFERHISTORY.ID.desc())
                .first()
            )
            if transfer and transfer[0]:
                return str(transfer[0])
            download = (
                db.query(DOWNLOADHISTORY.IDENTITY_ID)
                .filter(
                    DOWNLOADHISTORY.ANCHOR_PROVIDER == provider,
                    DOWNLOADHISTORY.ANCHOR_EXTERNAL_ID == external_id,
                    DOWNLOADHISTORY.IDENTITY_ID.isnot(None),
                )
                .order_by(DOWNLOADHISTORY.ID.desc())
                .first()
            )
            if download and download[0]:
                return str(download[0])
        return None

    def list_stale_running(self, before: datetime, limit: int = 500) -> list[MediaLifecycle]:
        with self.readonly() as db:
            return (
                db.query(MediaLifecycle)
                .filter(
                    MediaLifecycle.IDENTITY_ID != "preview",
                    MediaLifecycle.STATUS.in_(
                        [
                            LifecycleStatus.QUEUED.value,
                            LifecycleStatus.RUNNING.value,
                            LifecycleStatus.RETRYING.value,
                        ]
                    ),
                    MediaLifecycle.STAGE.in_(
                        [
                            LifecycleStage.DOWNLOAD_QUEUED.value,
                            LifecycleStage.DOWNLOADING.value,
                            LifecycleStage.TRANSFER_QUEUED.value,
                            LifecycleStage.TRANSFERRING.value,
                            LifecycleStage.SCRAPE_QUEUED.value,
                            LifecycleStage.SCRAPING.value,
                        ]
                    ),
                    MediaLifecycle.LAST_EVENT_AT < before,
                )
                .order_by(MediaLifecycle.LAST_EVENT_AT.asc())
                .limit(max(1, int(limit)))
                .all()
            )

    def list_blocked_downloads(self, limit: int = 500) -> list[MediaLifecycle]:
        """下载阶段被标记 blocked 的快照，供活跃下载心跳恢复."""
        with self.readonly() as db:
            return (
                db.query(MediaLifecycle)
                .filter(
                    MediaLifecycle.IDENTITY_ID != "preview",
                    MediaLifecycle.STATUS == LifecycleStatus.BLOCKED.value,
                    MediaLifecycle.STAGE.in_(
                        [
                            LifecycleStage.DOWNLOAD_QUEUED.value,
                            LifecycleStage.DOWNLOADING.value,
                        ]
                    ),
                )
                .order_by(MediaLifecycle.LAST_EVENT_AT.asc())
                .limit(max(1, int(limit)))
                .all()
            )

    def list_subscription_summaries(self, identity_id: str, *, user=None) -> list[dict[str, Any]]:
        """读取订阅侧总集数，用于补齐尚未进入生命周期记录的分集。"""
        with self.readonly() as db:
            query = db.query(SubscribeTvs).filter(SubscribeTvs.IDENTITY_ID == identity_id)
            if user is not None:
                query = apply_owner_scope(query, SubscribeTvs, user, include_shared=False)
            rows = query.order_by(SubscribeTvs.SEASON.asc()).all()
            episode_rows = (
                db.query(SubscribeTvEpisodes.RSSID, SubscribeTvEpisodes.EPISODES)
                .filter(SubscribeTvEpisodes.IDENTITY_ID == identity_id)
                .all()
            )
            missing_by_rss: dict[str, list[int]] = {}
            for rssid, value in episode_rows:
                missing_by_rss[str(rssid)] = [
                    int(part) for part in str(value or "").split(",") if part.strip().isdigit()
                ]
            result = []
            for row in rows:
                total = int(row.TOTAL or row.TOTAL_EP or 0)
                current = int(row.CURRENT_EP or 0)
                lack = int(row.LACK or 0)
                if total and 0 < current <= total:
                    lack = max(0, total - current + 1)
                result.append(
                    {
                        "season": row.SEASON,
                        "total_ep": total,
                        "current_ep": int(row.CURRENT_EP or 0),
                        "completed_ep": max(0, total - lack),
                        "missing_episodes": missing_by_rss.get(str(row.ID), []),
                        "state": row.STATE,
                        "name": row.NAME,
                        "year": getattr(row, "YEAR", None),
                        "anchor_provider": getattr(row, "ANCHOR_PROVIDER", None) or getattr(row, "PROVIDER", None),
                        "content_profile": getattr(row, "CONTENT_PROFILE", None),
                        "user_id": getattr(row, "USER_ID", None),
                    }
                )
            return result

    def stats_grouped(self, *, user=None) -> dict[str, Any]:
        with self.readonly() as db:
            query = db.query(MediaLifecycle).filter(MediaLifecycle.IDENTITY_ID != "preview")
            if user is not None:
                query = apply_owner_scope(query, MediaLifecycle, user, include_shared=False)
            rows = query.all()
            identities = list({str(row.IDENTITY_ID) for row in rows})
            grouped = _group_lifecycle_rows(rows)
            _apply_subscription_state(
                grouped,
                _subscription_map(db, identities),
                _active_subscription_identities(db, identities),
                _completed_subscription_identities(db, identities),
                _cancelled_subscription_identities(db, identities),
            )
            existing = {str(item.get("IDENTITY_ID") or "") for item in grouped}
            grouped.extend(_active_subscription_items(db, user, existing))
        by_status: dict[str, int] = {}
        by_stage: dict[str, int] = {}
        for item in grouped:
            by_status[item["STATUS"]] = by_status.get(item["STATUS"], 0) + 1
            by_stage[item["STAGE"]] = by_stage.get(item["STAGE"], 0) + 1
        return {"total": len(grouped), "by_status": by_status, "by_stage": by_stage}

    @staticmethod
    def event_payload(value: Any) -> str:
        return JsonUtils.dumps(JsonUtils.to_jsonable(value or {}))


def _active_subscription_items(db, user, existing: set[str]) -> list[dict[str, Any]]:
    """把当前活跃订阅补进读模型，避免没有生命周期事件时漏掉在途订阅."""
    result: list[dict[str, Any]] = []
    now = datetime.now()
    specs = ((SubscribeTvs, "tv"), (SubscribeMovies, "movie"))
    for model, default_type in specs:
        query = db.query(model).filter(
            model.STATE.in_(["D", "S", "R"]),
            model.IDENTITY_ID.isnot(None),
        )
        if user is not None:
            query = apply_owner_scope(query, model, user, include_shared=False)
        for row in query.all():
            identity_id = str(getattr(row, "IDENTITY_ID", "") or "")
            if not identity_id or identity_id in existing:
                continue
            total = int(getattr(row, "TOTAL", 0) or getattr(row, "TOTAL_EP", 0) or 0)
            current = int(getattr(row, "CURRENT_EP", 0) or 0)
            lack = int(getattr(row, "LACK", 0) or 0)
            if total and 0 < current <= total:
                lack = max(0, total - current + 1)
            completed = max(0, total - lack) if total else 0
            profile = str(getattr(row, "CONTENT_PROFILE", "") or "default")
            media_type = "anime" if profile == "anime" else default_type
            season_match = re.search(r"\d+", str(getattr(row, "SEASON", "") or ""))
            season = int(season_match.group()) if season_match else 0
            state = str(getattr(row, "STATE", "") or "")
            stage = LifecycleStage.SEARCHING.value if state == "S" else LifecycleStage.SUBSCRIBED.value
            result.append(
                {
                    "ID": 0,
                    "IDENTITY_ID": identity_id,
                    "MEDIA_TYPE": media_type,
                    "SEASON": season,
                    "EPISODE": 0,
                    "TITLE": getattr(row, "NAME", None),
                    "YEAR": getattr(row, "YEAR", None),
                    "POSTER": getattr(row, "POSTER", None) or getattr(row, "IMAGE", None),
                    "STAGE": stage,
                    "STATUS": "queued" if state == "D" else "running",
                    "RUN_ID": None,
                    "TRACE_ID": None,
                    "PROGRESS": round(completed * 100 / total) if total else 0,
                    "SOURCE_PROVIDER": getattr(row, "ANCHOR_PROVIDER", None) or getattr(row, "PROVIDER", None),
                    "CONTENT_PROFILE": profile,
                    "USER_ID": getattr(row, "USER_ID", None),
                    "STAGE_STARTED_AT": now,
                    "LAST_EVENT_AT": now,
                    "NEXT_RETRY_AT": None,
                    "RETRY_COUNT": 0,
                    "LAST_ERROR": None,
                    "EPISODE_COUNT": total or (1 if default_type == "movie" else 0),
                    "COMPLETED_EPISODES": completed,
                    "IN_LIBRARY_EPISODES": completed,
                    "SUBSCRIBED_EPISODES": completed,
                    "MISSING": False,
                    "ACTIVITY_AT": now,
                }
            )
    return result


def _active_subscription_identities(db, identities: list[str]) -> set[str]:
    """当前仍存在的订阅身份（含电影/剧集），用于识别已取消订阅."""
    if not identities:
        return set()
    active: set[str] = set()
    for model in (SubscribeTvs, SubscribeMovies):
        rows = (
            db.query(model.IDENTITY_ID)
            .filter(
                model.IDENTITY_ID.in_(identities),
                model.IDENTITY_ID.isnot(None),
            )
            .all()
        )
        active.update(str(row[0]) for row in rows if row[0])
    return active


def _completed_subscription_identities(db, identities: list[str]) -> set[str]:
    """已有完成订阅历史的身份，不能再被投影成“已取消”."""
    if not identities:
        return set()
    rows = (
        db.query(SubscribeHistory.IDENTITY_ID)
        .filter(
            SubscribeHistory.IDENTITY_ID.in_(identities),
            SubscribeHistory.IDENTITY_ID.isnot(None),
        )
        .all()
    )
    return {str(row[0]) for row in rows if row[0]}


def _cancelled_subscription_identities(db, identities: list[str]) -> set[str]:
    """根据最新订阅事件判断取消状态；后续 search.started 表示重新订阅."""
    if not identities:
        return set()
    rows = (
        db.query(MediaLifecycleEvent.IDENTITY_ID, MediaLifecycleEvent.EVENT_TYPE)
        .filter(
            MediaLifecycleEvent.IDENTITY_ID.in_(identities),
            MediaLifecycleEvent.EVENT_TYPE.in_(["search.started", "subscribe.cancelled", "subscribe.completed"]),
        )
        .order_by(MediaLifecycleEvent.ID.asc())
        .all()
    )
    latest: dict[str, str] = {}
    for identity, event_type in rows:
        if identity:
            latest[str(identity)] = str(event_type)
    return {identity for identity, event_type in latest.items() if event_type == "subscribe.cancelled"}


def _subscription_map(db, identities: list[str]) -> dict[str, tuple[int, str, int]]:
    if not identities:
        return {}
    subscriptions = (
        db.query(
            SubscribeTvs.IDENTITY_ID,
            SubscribeTvs.TOTAL_EP,
            SubscribeTvs.TOTAL,
            SubscribeTvs.CURRENT_EP,
            SubscribeTvs.LACK,
            SubscribeTvs.STATE,
        )
        .filter(SubscribeTvs.IDENTITY_ID.in_(identities))
        .all()
    )
    result: dict[str, tuple[int, str, int]] = {}
    for identity, total_ep, total, current_ep, lack, sub_state in subscriptions:
        if not identity:
            continue
        key = str(identity)
        total_value = int(total or total_ep or 0)
        current_value = int(current_ep or 0)
        lack_value = int(lack or 0)
        if total_value and 0 < current_value <= total_value:
            lack_value = max(0, total_value - current_value + 1)
        completed_value = max(0, total_value - lack_value)
        previous = result.get(key)
        if previous is None or total_value > previous[0]:
            result[key] = (total_value, str(sub_state or ""), completed_value)
    return result


def _apply_subscription_state(
    grouped: list[dict[str, Any]],
    subscription_map: dict[str, tuple[int, str, int]],
    active_identities: set[str] | None = None,
    completed_identities: set[str] | None = None,
    cancelled_identities: set[str] | None = None,
) -> None:
    """用订阅总集数约束整季状态，避免只统计已产生生命周期记录的分集。"""
    active_identities = active_identities or set()
    completed_identities = completed_identities or set()
    cancelled_identities = cancelled_identities or set()
    for item in grouped:
        identity = str(item.get("IDENTITY_ID") or "")
        sub = subscription_map.get(identity)
        if (
            identity not in active_identities
            and identity in cancelled_identities
            and str(item.get("STAGE") or "") != LifecycleStage.IN_LIBRARY.value
        ):
            item["STATUS"] = LifecycleStatus.CANCELLED.value
            continue
        if not sub:
            # 订阅已取消/删除但生命周期仍停在订阅中：投影为已取消，不保留“进行中”假象。
            if (
                identity not in active_identities
                and identity not in completed_identities
                and str(item.get("STAGE") or "") in {LifecycleStage.SUBSCRIBED.value, LifecycleStage.SEARCHING.value}
                and str(item.get("STATUS") or "")
                in {
                    LifecycleStatus.QUEUED.value,
                    LifecycleStatus.RUNNING.value,
                    LifecycleStatus.RETRYING.value,
                }
            ):
                item["STATUS"] = LifecycleStatus.CANCELLED.value
            continue
        total_ep, sub_state, subscribed_episodes = sub
        completed = int(item.get("COMPLETED_EPISODES") or 0)
        if total_ep > 0:
            item["EPISODE_COUNT"] = max(int(item.get("EPISODE_COUNT") or 0), total_ep)
            completed = min(total_ep, completed)
            item["COMPLETED_EPISODES"] = completed
            item["SUBSCRIBED_EPISODES"] = min(total_ep, subscribed_episodes)
            item["PROGRESS"] = round(completed * 100 / total_ep)
        if sub_state in {"D", "S", "R"}:
            # 活跃订阅只在存在真实队列任务时进入下载/转移/刮削阶段；
            # 已刮削/已入库的分集保留终态，避免把“等待下一集”覆盖成订阅中。
            active_stage = str(item.get("ACTIVE_STAGE") or "")
            stage_value = str(item.get("STAGE") or "")
            terminal = {LifecycleStage.SCRAPED.value, LifecycleStage.IN_LIBRARY.value}
            if active_stage:
                item["STAGE"] = active_stage
                item["STATUS"] = "queued" if sub_state == "D" else "running"
            elif stage_value not in terminal:
                item["STAGE"] = LifecycleStage.SUBSCRIBED.value
                item["STATUS"] = "queued" if sub_state == "D" else "running"
            elif item.get("STATUS") == LifecycleStatus.SUCCEEDED.value:
                # 订阅仍活跃，只是最新一集已入库；保留已入库阶段，
                # 但状态回到进行中，避免整部剧从“进行中”列表消失。
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
        active_items = [
            item
            for item in state_items
            if item.STATUS
            in {
                LifecycleStatus.QUEUED.value,
                LifecycleStatus.RUNNING.value,
                LifecycleStatus.RETRYING.value,
            }
            and stage_rank(item.STAGE) >= stage_rank(LifecycleStage.DOWNLOAD_QUEUED.value)
        ]
        data = representative.as_dict()
        data["ACTIVE_STAGE"] = max(active_items, key=lambda item: stage_rank(item.STAGE)).STAGE if active_items else ""
        if status == LifecycleStatus.SUCCEEDED.value and stage not in {
            LifecycleStage.SCRAPED.value,
            LifecycleStage.IN_LIBRARY.value,
        }:
            status = LifecycleStatus.RUNNING.value
        if episode_items:
            data["SEASON"] = max(int(item.SEASON or 0) for item in episode_items)
            data["EPISODE"] = max(int(item.EPISODE or 0) for item in episode_items)
        providers = [
            str(item.SOURCE_PROVIDER) for item in state_items if item.SOURCE_PROVIDER not in {None, "", "content_id"}
        ]
        if providers:
            data["SOURCE_PROVIDER"] = providers[0]
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

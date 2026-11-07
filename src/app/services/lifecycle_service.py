"""媒体生命周期投影服务（ADR-026）."""

from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import log
from app.core.settings import settings
from app.db.models.download import DOWNLOADHISTORY
from app.db.models.lifecycle import MediaLifecycleEvent
from app.db.models.media_sync import MEDIASYNCITEMS
from app.db.models.subscribe import SubscribeHistory
from app.db.models.transfer import TRANSFERHISTORY
from app.db.repositories.base_repository import BaseRepository
from app.db.repositories.download_repository import DownloadRepository
from app.db.repositories.lifecycle_repository import LifecycleRepository
from app.db.repositories.media_identity_repository import MediaIdentityRepository
from app.domain.lifecycle import LifecycleStage, LifecycleStatus, map_download_state, map_task_status
from app.domain.media_types import media_type_registry
from app.media.display_image_policy import unwrap_display_image_url
from app.services.identity_resolver import IdentityResolver
from app.services.series_service import SeriesService


class LifecycleProjector:
    """唯一写入生命周期读模型的服务.

    只做投影，不驱动下载/转移/刮削业务。
    """

    def __init__(self, repository: LifecycleRepository | None = None):
        self._repo = repository or LifecycleRepository()
        self._resolver = IdentityResolver()
        self._identity_repo = MediaIdentityRepository()

    def is_in_library(self, media) -> bool:
        """判断该媒体（季包则逐集）是否已经处于入库成功状态。"""
        try:
            resolved = self._resolver.resolve_media(media, allow_local=True)
            identity_id = resolved.identity_id
            season = 0
            if hasattr(media, "get_season_seq"):
                season = int(media.get_season_seq() or 0)
            episodes = list(media.get_episode_list()) if hasattr(media, "get_episode_list") else []
            for episode in episodes or [0]:
                current = self._repo.get_current(identity_id, season=season, episode=int(episode or 0))
                if current is None:
                    return False
                if (
                    str(getattr(current, "STAGE", "") or "") != LifecycleStage.IN_LIBRARY.value
                    or str(getattr(current, "STATUS", "") or "") != LifecycleStatus.SUCCEEDED.value
                ):
                    return False
            return True
        except Exception:  # noqa: BLE001 - 判断失败按未入库处理，保证正常通知
            return False

    def record(
        self,
        *,
        identity_id: str,
        series_key: str | None = None,
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
        update_snapshot: bool = True,
    ) -> bool:
        if not identity_id:
            raise ValueError("identity_id is required")
        occurred = occurred_at or datetime.now()
        stage_value = LifecycleStage(stage).value
        status_value = LifecycleStatus(status).value
        resolved_type = media_type_registry.resolve_profile(content_profile) or media_type_registry.resolve(
            media_type, content_profile
        )
        if resolved_type.key != "unknown":
            media_type = resolved_type.key
        key = event_key or self._event_key(identity_id, season, episode, stage_value, event_type, trace_id, occurred)
        poster = unwrap_display_image_url(poster) if poster else poster
        if str(identity_id or "") and str(identity_id) != "preview" and not source_provider:
            ref = self._identity_repo.get_display_ref(str(identity_id))
            if ref is not None:
                source_provider = str(ref.PROVIDER or "")
        if str(identity_id or "") and str(identity_id) != "preview" and not content_profile:
            identity = self._identity_repo.get_identity(str(identity_id))
            if identity is not None and identity.CONTENT_PROFILE:
                content_profile = str(identity.CONTENT_PROFILE)
        terminal_progress_stages = {
            LifecycleStage.DOWNLOADED.value,
            LifecycleStage.TRANSFERRED.value,
            LifecycleStage.SCRAPED.value,
            LifecycleStage.IN_LIBRARY.value,
        }
        if (
            progress is None
            and stage_value in terminal_progress_stages
            and status_value == LifecycleStatus.SUCCEEDED.value
        ):
            progress = 100
        event = MediaLifecycleEvent(
            EVENT_KEY=key,
            IDENTITY_ID=identity_id,
            SERIES_KEY=series_key,
            MEDIA_TYPE=media_type or "unknown",
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
            "SERIES_KEY": series_key,
            "MEDIA_TYPE": media_type or "unknown",
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
            created = self._repo.record_event(event, snapshot, update_snapshot=update_snapshot)
            if created:
                log.debug(
                    f"[Lifecycle]记录事件 {event_type} identity={identity_id} stage={stage_value} status={status_value}"
                )
            return created
        except Exception as exc:  # noqa: BLE001 - 生命周期失败不影响业务
            log.warn(f"[Lifecycle]写入生命周期事件失败: {exc}")
            return False

    def record_subscription_outcome(
        self,
        *,
        identity_id: str,
        status: LifecycleStatus | str,
        event_type: str,
        media_type: str = "tv",
        season: int = 0,
        title: str | None = None,
        year: str | None = None,
        poster: str | None = None,
        series_key: str | None = None,
        source_provider: str | None = None,
        content_profile: str | None = None,
        user_id: int | None = None,
        message: str | None = None,
        payload: dict[str, Any] | None = None,
        event_key: str | None = None,
    ) -> bool:
        """记录订阅取消/完成结果；沿用当前阶段，避免被单调阶段规则吞掉."""
        current = self._repo.get_current(identity_id, season=season, episode=0)
        current_stage = str(getattr(current, "STAGE", "") or "")
        if str(status) == LifecycleStatus.CANCELLED.value and current_stage == LifecycleStage.IN_LIBRARY.value:
            return False
        stage = current_stage or (
            LifecycleStage.SUBSCRIBED.value
            if str(status) == LifecycleStatus.CANCELLED.value
            else LifecycleStage.DOWNLOADED.value
        )
        return self.record(
            identity_id=identity_id,
            series_key=series_key,
            stage=stage,
            status=status,
            event_type=event_type,
            media_type=media_type,
            season=season,
            episode=0,
            title=title,
            year=year,
            poster=poster,
            progress=100 if str(status) == LifecycleStatus.SUCCEEDED.value else None,
            source_provider=source_provider,
            content_profile=content_profile,
            user_id=user_id,
            message=message,
            payload=payload,
            event_key=event_key,
        )

    def record_media(
        self,
        media: Any,
        *,
        stage: LifecycleStage | str,
        status: LifecycleStatus | str,
        event_type: str,
        run_id: str | None = None,
        trace_id: str | None = None,
        progress: int | None = None,
        retry_count: int = 0,
        next_retry_at: datetime | None = None,
        error: str | None = None,
        message: str | None = None,
        payload: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
        event_key: str | None = None,
    ) -> bool:
        """从 MediaInfo 投影事件；没有稳定身份时跳过，不影响业务."""
        media_type = (
            str(getattr(media, "media_type_key", "") or "")
            or getattr(getattr(media, "type", None), "value", getattr(media, "type", ""))
            or "unknown"
        )
        season = 0
        if hasattr(media, "get_season_seq"):
            try:
                season = int(media.get_season_seq() or 0)
            except (TypeError, ValueError):
                season = 0
        episodes = list(media.get_episode_list()) if hasattr(media, "get_episode_list") else []
        if not episodes:
            episodes = [0]
        resolved = self._resolver.resolve_media(media, allow_local=True)
        identity_id = resolved.identity_id
        if not identity_id or identity_id == "preview":
            return False
        provider = resolved.provider
        content_profile = resolved.content_profile
        try:
            series_key = SeriesService().ensure_media_series(media)
        except Exception:  # noqa: BLE001
            series_key = getattr(media, "series_key", None)
        created_any = False
        for episode in episodes:
            episode_key = f"{event_key}:{episode}" if event_key and len(episodes) > 1 else event_key
            created_any = (
                self.record(
                    identity_id=identity_id,
                    series_key=series_key,
                    stage=stage,
                    status=status,
                    event_type=event_type,
                    media_type=str(media_type),
                    season=season,
                    episode=int(episode or 0),
                    run_id=run_id,
                    trace_id=trace_id,
                    title=str(getattr(media, "title", "") or "") or None,
                    year=str(getattr(media, "year", "") or "") or None,
                    poster=str(getattr(media, "poster_path", "") or "") or None,
                    progress=progress,
                    source_provider=provider or None,
                    content_profile=content_profile or None,
                    user_id=getattr(media, "user_id", None),
                    retry_count=retry_count,
                    next_retry_at=next_retry_at,
                    error=error,
                    message=message,
                    payload=payload,
                    occurred_at=occurred_at,
                    event_key=episode_key,
                )
                or created_any
            )
        return created_any

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


class LifecycleReconciler:
    """从现有历史表回填生命周期；用于事件缺失/重启恢复/首次上线."""

    def __init__(self, projector: LifecycleProjector | None = None):
        self._projector = projector or LifecycleProjector()
        self._resolver = IdentityResolver()

    def reconcile_recent(self, limit: int = 500) -> dict[str, int]:
        count = 0
        with BaseRepository().readonly() as db:
            downloads = db.query(DOWNLOADHISTORY).order_by(DOWNLOADHISTORY.ID.desc()).limit(max(1, int(limit))).all()
            transfers = db.query(TRANSFERHISTORY).order_by(TRANSFERHISTORY.ID.desc()).limit(max(1, int(limit))).all()
            subscriptions = (
                db.query(SubscribeHistory).order_by(SubscribeHistory.ID.desc()).limit(max(1, int(limit))).all()
            )
            sync_rows = db.query(
                MEDIASYNCITEMS.IDENTITY_ID,
                MEDIASYNCITEMS.TITLE,
                MEDIASYNCITEMS.ORGIN_TITLE,
                MEDIASYNCITEMS.PATH,
                MEDIASYNCITEMS.ITEM_TYPE,
                MEDIASYNCITEMS.YEAR,
                MEDIASYNCITEMS.ANCHOR_PROVIDER,
                MEDIASYNCITEMS.CONTENT_PROFILE,
            ).all()
            in_library_ids = {str(item[0]) for item in sync_rows if item[0]}
            in_library_tokens: set[str] = set()
            for row in sync_rows:
                for text in (row[1], row[2], row[3]):
                    token = _library_token(text)
                    if token:
                        in_library_tokens.add(token)
            lifecycle_repo = LifecycleRepository()
            sync_active = DownloadRepository().get_active_download_states(in_library_ids)
            for identity_id, title, origin_title, _path, item_type, year, provider, profile in sync_rows:
                if not identity_id or str(identity_id) in sync_active:
                    continue
                current = lifecycle_repo.get_current(str(identity_id))
                if (
                    current is not None
                    and str(current.STAGE) == LifecycleStage.IN_LIBRARY.value
                    and str(current.STATUS) == LifecycleStatus.SUCCEEDED.value
                ):
                    continue
                if current is not None and (
                    str(current.STAGE)
                    in {
                        LifecycleStage.DOWNLOAD_QUEUED.value,
                        LifecycleStage.DOWNLOADING.value,
                        LifecycleStage.TRANSFER_QUEUED.value,
                        LifecycleStage.TRANSFERRING.value,
                        LifecycleStage.SCRAPE_QUEUED.value,
                        LifecycleStage.SCRAPING.value,
                    }
                    and str(current.STATUS)
                    in {
                        LifecycleStatus.QUEUED.value,
                        LifecycleStatus.RUNNING.value,
                        LifecycleStatus.RETRYING.value,
                    }
                ):
                    continue
                media_type = "tv" if str(item_type or "").lower() in {"episode", "series", "season", "tv"} else "movie"
                if self._projector.record(
                    identity_id=str(identity_id),
                    stage=LifecycleStage.IN_LIBRARY,
                    status=LifecycleStatus.SUCCEEDED,
                    event_type="reconcile.library.sync",
                    media_type=media_type,
                    title=title or origin_title,
                    year=year,
                    source_provider=provider,
                    content_profile=profile,
                    progress=100,
                    message="媒体库同步索引已存在",
                    payload={"source": "MEDIASYNC_ITEMS"},
                    occurred_at=datetime.now(),
                    event_key=f"library-sync:{identity_id}",
                ):
                    count += 1
            identity_by_external: dict[str, str] = {}
            identity_by_title: dict[tuple[str, str, str], str] = {}
            for row in downloads:
                identity_id = _valid_identity(row.IDENTITY_ID)
                if not identity_id:
                    continue
                external_id = str(row.ANCHOR_EXTERNAL_ID or "")
                if external_id:
                    identity_by_external.setdefault(external_id, identity_id)
                identity_by_title.setdefault(
                    (str(row.TITLE or "").lower(), str(row.YEAR or ""), str(row.SE or "")),
                    identity_id,
                )
            for row in reversed(downloads):
                identity_id = _canonical_identity(row, identity_by_external, identity_by_title, self._resolver)
                if not identity_id:
                    continue
                stage, status = map_download_state(row.STATE)
                episode_pairs = _parse_season_episodes(row.SE)
                occurred = _parse_history_time(row.DATE)
                for season, episode in episode_pairs:
                    event_key = f"download-history:{row.ID}:{row.STATE}"
                    if len(episode_pairs) > 1:
                        event_key = f"{event_key}:{season}:{episode}"
                    if self._projector.record(
                        identity_id=identity_id,
                        stage=stage,
                        status=status,
                        event_type=f"reconcile.download.{str(row.STATE).lower()}",
                        media_type=_row_media_type(row.TYPE),
                        season=season,
                        episode=episode,
                        run_id=f"download-history:{row.ID}",
                        trace_id=f"media:{identity_id}",
                        title=row.TITLE,
                        year=row.YEAR,
                        poster=row.POSTER,
                        source_provider=row.ANCHOR_PROVIDER,
                        content_profile=row.CONTENT_PROFILE,
                        user_id=row.USER_ID,
                        message=f"从下载历史回填: {row.STATE}",
                        payload={"source": "DOWNLOAD_HISTORY", "id": row.ID},
                        occurred_at=occurred,
                        event_key=event_key,
                    ):
                        count += 1
            for row in reversed(subscriptions):
                identity_id = _canonical_identity(row, identity_by_external, identity_by_title, self._resolver)
                if not identity_id:
                    continue
                occurred = _parse_history_time(row.FINISH_TIME)
                if self._projector.record(
                    identity_id=identity_id,
                    stage=LifecycleStage.SUBSCRIBED,
                    status=LifecycleStatus.SUCCEEDED,
                    event_type="reconcile.subscribe.completed",
                    media_type=_row_media_type(row.TYPE),
                    title=row.NAME,
                    year=row.YEAR,
                    source_provider=row.ANCHOR_PROVIDER,
                    content_profile=row.CONTENT_PROFILE,
                    user_id=row.USER_ID,
                    run_id=f"subscribe-history:{row.ID}",
                    trace_id=f"media:{identity_id}",
                    message="从订阅历史回填",
                    payload={"source": "SUBSCRIBE_HISTORY", "id": row.ID},
                    occurred_at=occurred,
                    event_key=f"subscribe-history:{row.ID}",
                    update_snapshot=False,
                ):
                    count += 1

            for row in reversed(transfers):
                episode_pairs = _parse_season_episodes(row.SEASON_EPISODE)
                occurred = _parse_history_time(row.DATE)
                failed = str(row.DEST_STATE or "") in {"missing", "deleted"}
                identity_id = _canonical_identity(row, identity_by_external, identity_by_title, self._resolver)
                if not identity_id:
                    continue
                for season, episode in episode_pairs:
                    if self._projector.record(
                        identity_id=identity_id,
                        stage=LifecycleStage.TRANSFERRED,
                        status=LifecycleStatus.FAILED if failed else LifecycleStatus.SUCCEEDED,
                        event_type="reconcile.transfer.failed" if failed else "reconcile.transfer.completed",
                        media_type=_row_media_type(row.TYPE),
                        season=season,
                        episode=episode,
                        run_id=f"transfer-history:{row.ID}",
                        trace_id=f"media:{identity_id}",
                        title=row.TITLE,
                        year=row.YEAR,
                        poster=row.POSTER,
                        source_provider=row.ANCHOR_PROVIDER,
                        content_profile=row.CONTENT_PROFILE,
                        message="从转移历史回填",
                        payload={"source": "TRANSFER_HISTORY", "id": row.ID},
                        occurred_at=occurred,
                        event_key=_scoped_event_key(
                            f"transfer-history:{row.ID}:{season}:{episode}"
                            if len(episode_pairs) > 1
                            else f"transfer-history:{row.ID}",
                            row.IDENTITY_ID,
                            identity_id,
                        ),
                    ):
                        count += 1
                if failed:
                    continue
                target = Path(str(row.DEST_PATH or row.DEST or ""))
                if target.is_file():
                    target = target.parent
                nfo_time = _find_nfo_time(target)
                has_media = _has_media_file(target)
                if nfo_time is not None and has_media:
                    for season, episode in episode_pairs:
                        if self._projector.record(
                            identity_id=identity_id,
                            stage=LifecycleStage.SCRAPED,
                            status=LifecycleStatus.SUCCEEDED,
                            event_type="reconcile.scrape.completed",
                            media_type=_row_media_type(row.TYPE),
                            season=season,
                            episode=episode,
                            run_id=f"transfer-history:{row.ID}",
                            trace_id=f"media:{identity_id}",
                            title=row.TITLE,
                            year=row.YEAR,
                            poster=row.POSTER,
                            source_provider=row.ANCHOR_PROVIDER,
                            content_profile=row.CONTENT_PROFILE,
                            message="从目标目录 NFO 回填",
                            payload={"source": "NFO", "path": str(target)},
                            occurred_at=nfo_time,
                            event_key=_scoped_event_key(
                                f"scrape-history:{row.ID}:{season}:{episode}"
                                if len(episode_pairs) > 1
                                else f"scrape-history:{row.ID}",
                                row.IDENTITY_ID,
                                identity_id,
                            ),
                        ):
                            count += 1
                # 与 LibraryPresenceService 保持一致：转移历史命中即可视为库内存在。
                # 这里再要求 NFO 已生成，确保至少完成元数据落盘。
                if has_media and (
                    nfo_time is not None or identity_id in in_library_ids or _matches_library(target, in_library_tokens)
                ):
                    library_occurred = (nfo_time or occurred or datetime.now()) + timedelta(seconds=1)
                    for season, episode in episode_pairs:
                        if self._projector.record(
                            identity_id=identity_id,
                            stage=LifecycleStage.IN_LIBRARY,
                            status=LifecycleStatus.SUCCEEDED,
                            event_type="reconcile.library.present",
                            media_type=_row_media_type(row.TYPE),
                            season=season,
                            episode=episode,
                            run_id=f"transfer-history:{row.ID}",
                            trace_id=f"media:{identity_id}",
                            title=row.TITLE,
                            year=row.YEAR,
                            poster=row.POSTER,
                            source_provider=row.ANCHOR_PROVIDER,
                            content_profile=row.CONTENT_PROFILE,
                            message="从媒体同步索引回填",
                            payload={"source": "MEDIASYNC_ITEMS"},
                            occurred_at=library_occurred,
                            event_key=_scoped_event_key(
                                f"library-history:{row.ID}:{season}:{episode}"
                                if len(episode_pairs) > 1
                                else f"library-history:{row.ID}",
                                row.IDENTITY_ID,
                                identity_id,
                            ),
                        ):
                            count += 1

            # 媒体库中可能存在没有转移历史的分集（手工放入、旧任务丢失等），
            # 用转移目标目录里的 NFO + 视频文件直接回填 in_library。
            scanned_library: set[tuple[str, int, int]] = set()
            for row in transfers:
                identity_id = _canonical_identity(row, identity_by_external, identity_by_title, self._resolver)
                if not identity_id:
                    continue
                target = Path(str(row.DEST_PATH or row.DEST or ""))
                if target.is_file():
                    target = target.parent
                if not target.is_dir():
                    continue
                for nfo in target.glob("*.nfo"):
                    match = re.search(r"S(\d+)E(\d+)", nfo.stem, re.IGNORECASE)
                    if not match:
                        continue
                    season, episode = int(match.group(1)), int(match.group(2))
                    key = (identity_id, season, episode)
                    if key in scanned_library:
                        continue
                    if not any(nfo.with_suffix(ext).is_file() for ext in (".mp4", ".mkv", ".ts", ".avi")):
                        continue
                    try:
                        occurred = datetime.fromtimestamp(nfo.stat().st_mtime)
                    except OSError:
                        continue
                    scanned_library.add(key)
                    if self._projector.record(
                        identity_id=identity_id,
                        stage=LifecycleStage.IN_LIBRARY,
                        status=LifecycleStatus.SUCCEEDED,
                        event_type="reconcile.library.scanned",
                        media_type=_row_media_type(row.TYPE),
                        season=season,
                        episode=episode,
                        run_id=f"library-scan:{row.ID}",
                        trace_id=f"media:{identity_id}",
                        title=row.TITLE,
                        year=row.YEAR,
                        poster=row.POSTER,
                        source_provider=row.ANCHOR_PROVIDER,
                        content_profile=row.CONTENT_PROFILE,
                        message="从媒体目录扫描回填",
                        payload={"source": "LIBRARY_SCAN", "path": str(nfo)},
                        occurred_at=occurred,
                        event_key=f"library-scan:{identity_id}:{season}:{episode}",
                    ):
                        count += 1
        stale_hours = int((settings.get("queue") or {}).get("lifecycle_stale_hours", 24) or 0)
        download_stages = {
            LifecycleStage.DOWNLOAD_QUEUED.value,
            LifecycleStage.DOWNLOADING.value,
        }
        lifecycle_repo = LifecycleRepository()
        stale_rows = lifecycle_repo.list_stale_running(datetime.now() - timedelta(hours=stale_hours or 24))
        blocked_rows = lifecycle_repo.list_blocked_downloads()
        active_downloads = DownloadRepository().get_active_download_states(
            {str(row.IDENTITY_ID) for row in stale_rows} | {str(row.IDENTITY_ID) for row in blocked_rows}
        )
        if stale_hours > 0:
            before = datetime.now() - timedelta(hours=stale_hours)
            for row in LifecycleRepository().list_stale_running(before):
                active_state = active_downloads.get(str(row.IDENTITY_ID))
                if active_state and str(row.STAGE) in download_stages:
                    stage, status = map_download_state(active_state)
                    if self._projector.record(
                        identity_id=str(row.IDENTITY_ID),
                        stage=stage.value,
                        status=status.value,
                        event_type="download.progress",
                        media_type=str(row.MEDIA_TYPE or "unknown"),
                        season=int(row.SEASON or 0),
                        episode=int(row.EPISODE or 0),
                        run_id=str(row.RUN_ID or ""),
                        trace_id=str(row.TRACE_ID or ""),
                        title=row.TITLE,
                        year=row.YEAR,
                        poster=row.POSTER,
                        progress=int(row.PROGRESS or 0),
                        source_provider=row.SOURCE_PROVIDER,
                        content_profile=row.CONTENT_PROFILE,
                        user_id=row.USER_ID,
                        message="下载器任务仍活跃",
                        occurred_at=datetime.now(),
                        event_key=f"heartbeat:{row.IDENTITY_ID}:{row.SEASON}:{row.EPISODE}:{datetime.now():%Y%m%d%H%M}",
                    ):
                        count += 1
                    continue
                if self._projector.record(
                    identity_id=str(row.IDENTITY_ID),
                    stage=str(row.STAGE),
                    status=LifecycleStatus.BLOCKED,
                    event_type="reconcile.stale",
                    media_type=str(row.MEDIA_TYPE or "unknown"),
                    season=int(row.SEASON or 0),
                    episode=int(row.EPISODE or 0),
                    run_id=str(row.RUN_ID or ""),
                    trace_id=str(row.TRACE_ID or ""),
                    title=row.TITLE,
                    year=row.YEAR,
                    poster=row.POSTER,
                    source_provider=row.SOURCE_PROVIDER,
                    content_profile=row.CONTENT_PROFILE,
                    user_id=row.USER_ID,
                    message=f"超过 {stale_hours} 小时没有任务更新，已标记为停滞",
                    occurred_at=datetime.now(),
                    event_key=f"stale:{row.IDENTITY_ID}:{row.SEASON}:{row.EPISODE}:{row.LAST_EVENT_AT.isoformat()}",
                ):
                    count += 1
        # 已 blocked 但下载器任务仍活跃：心跳恢复为 downloading，避免误判停滞
        if active_downloads:
            for identity_id, active_state in active_downloads.items():
                snapshots = LifecycleRepository().list_identity_rows(identity_id)
                for snapshot in snapshots:
                    if (
                        str(snapshot.STAGE) not in download_stages
                        or str(snapshot.STATUS) != LifecycleStatus.BLOCKED.value
                    ):
                        continue
                    stage, status = map_download_state(active_state)
                    if self._projector.record(
                        identity_id=identity_id,
                        stage=stage.value,
                        status=status.value,
                        event_type="download.progress",
                        media_type=str(snapshot.MEDIA_TYPE or "unknown"),
                        season=int(snapshot.SEASON or 0),
                        episode=int(snapshot.EPISODE or 0),
                        run_id=str(snapshot.RUN_ID or ""),
                        trace_id=str(snapshot.TRACE_ID or ""),
                        title=snapshot.TITLE,
                        year=snapshot.YEAR,
                        poster=snapshot.POSTER,
                        progress=int(snapshot.PROGRESS or 0),
                        source_provider=snapshot.SOURCE_PROVIDER,
                        content_profile=snapshot.CONTENT_PROFILE,
                        user_id=snapshot.USER_ID,
                        message="下载器任务仍活跃",
                        occurred_at=datetime.now(),
                        event_key=f"heartbeat:{identity_id}:{snapshot.SEASON}:{snapshot.EPISODE}:{datetime.now():%Y%m%d%H%M}",
                    ):
                        count += 1
        return {"imported": count}


def _valid_identity(value: Any) -> str:
    text = str(value or "")
    return "" if text.lower() in {"", "preview"} else text


def _canonical_identity(
    row: Any,
    by_external: dict[str, str],
    by_title: dict[tuple[str, str, str], str],
    resolver: IdentityResolver,
) -> str:
    """优先按 anchor 归并历史表中的重复/占位 identity。"""
    external_id = str(getattr(row, "ANCHOR_EXTERNAL_ID", "") or "")
    if external_id and external_id in by_external:
        return by_external[external_id]
    identity_id = _valid_identity(getattr(row, "IDENTITY_ID", None))
    if identity_id:
        return identity_id
    key = (
        str(getattr(row, "TITLE", "") or "").lower(),
        str(getattr(row, "YEAR", "") or ""),
        str(getattr(row, "SE", None) or getattr(row, "SEASON_EPISODE", "") or ""),
    )
    matched = by_title.get(key, "")
    if matched:
        return matched
    resolved = resolver.resolve_values(
        identity_id=getattr(row, "IDENTITY_ID", None),
        provider=getattr(row, "ANCHOR_PROVIDER", None),
        external_id=getattr(row, "ANCHOR_EXTERNAL_ID", None),
        title=getattr(row, "TITLE", "") or getattr(row, "NAME", "") or "",
        year=getattr(row, "YEAR", None),
        media_type=_row_media_type(getattr(row, "TYPE", None)),
        allow_local=True,
    )
    return resolved.identity_id


def _scoped_event_key(base: str, row_identity: Any, canonical_identity: str) -> str:
    # 事件键必须只由历史记录本身决定；identity 归一后不能产生第二份同一事件。
    return base


def _library_token(value: Any) -> str:
    text = str(value or "").upper()
    if not text:
        return ""
    candidate = Path(text)
    if candidate.suffix or "/" in text:
        return (candidate.parent.name if candidate.suffix else candidate.name).upper()
    match = re.search(r"[A-Z0-9]{2,}[-_]\d{2,}", text)
    return match.group(0) if match else ""


def _matches_library(path: Path, tokens: set[str]) -> bool:
    name = path.name.upper()
    if not name:
        return False
    return any(token and token in name for token in tokens)


_MEDIA_SUFFIXES = {".mp4", ".mkv", ".avi", ".ts", ".m2ts", ".mov", ".wmv", ".flv", ".webm"}


def _has_media_file(path: Path) -> bool:
    try:
        return path.is_dir() and any(
            item.is_file() and item.suffix.lower() in _MEDIA_SUFFIXES for item in path.iterdir()
        )
    except OSError:
        return False


def _find_nfo_time(path: Path) -> datetime | None:
    try:
        if not path or not path.is_dir():
            return None
        nfo = next(path.glob("*.nfo"), None)
        if nfo is None or not nfo.is_file():
            return None
        return datetime.fromtimestamp(os.path.getmtime(nfo))
    except OSError:
        return None


def _parse_season_episodes(value: Any) -> list[tuple[int, int]]:
    text = str(value or "")
    pairs: list[tuple[int, int]] = []
    for match in re.finditer(r"S(\d+)\s*E(\d+)(?:\s*[-~]\s*E?(\d+))?", text, re.IGNORECASE):
        season = int(match.group(1))
        start = int(match.group(2))
        end = int(match.group(3) or start)
        if end < start:
            end = start
        pairs.extend((season, episode) for episode in range(start, min(end, start + 200) + 1))
    return pairs or [(0, 0)]


def _parse_season_episode(value: Any) -> tuple[int, int]:
    return _parse_season_episodes(value)[0]


def _parse_history_time(value: Any) -> datetime | None:
    text = str(value or "")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _row_media_type(value: Any) -> str:
    key = str(value or "").lower()
    return {"mov": "movie", "movie": "movie", "tv": "tv", "ani": "anime", "anime": "anime"}.get(
        key, str(value or "unknown")
    )

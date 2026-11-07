"""下载领域事件处理器."""

import os
import re

import log
from app.db.repositories.download_repository import DownloadRepository
from app.domain.lifecycle import LifecycleStage, LifecycleStatus
from app.events import Event, on_event
from app.events.constants import DOWNLOAD_COMPLETED, DOWNLOAD_FAILED, DOWNLOAD_STARTED
from app.events.payloads import DownloadCompletedPayload, DownloadFailedPayload, DownloadStartedPayload
from app.media.models import MediaInfo
from app.services.download_event_queue import publish_download_event
from app.services.identity_resolver import IdentityResolver
from app.services.lifecycle_service import LifecycleProjector


def _record_download(
    media: MediaInfo, stage: LifecycleStage, status: LifecycleStatus, event_type: str, **kwargs
) -> None:
    try:
        LifecycleProjector().record_media(media, stage=stage, status=status, event_type=event_type, **kwargs)
    except Exception as exc:  # noqa: BLE001 - 生命周期失败不影响下载
        log.warn(f"[Lifecycle]记录下载生命周期失败: {exc}")


@on_event(DOWNLOAD_STARTED)
def handle_download_started(event: Event) -> None:
    """下载开始事件处理器"""
    payload = event.payload
    if not isinstance(payload, DownloadStartedPayload):
        payload = DownloadStartedPayload(**payload)
    media = MediaInfo.model_validate(payload.media_info or {})
    _record_download(
        media,
        LifecycleStage.DOWNLOADING,
        LifecycleStatus.RUNNING,
        "download.started",
        run_id=payload.download_id,
        trace_id=f"download:{payload.download_id}" if payload.download_id else None,
        payload={
            "downloader_id": payload.downloader_id,
            "download_id": payload.download_id,
            "source": "DOWNLOAD_STARTED",
        },
    )
    log.info(f"[Event]下载开始: {payload.media_info.get('title')}")
    publish_download_event(
        {
            "event": DOWNLOAD_STARTED,
            "data": {
                "downloader_id": payload.downloader_id,
                "download_id": payload.download_id,
                "title": payload.media_info.get("title"),
            },
        }
    )


@on_event(DOWNLOAD_FAILED)
def handle_download_failed(event: Event) -> None:
    """下载失败事件处理器"""
    payload = event.payload
    if not isinstance(payload, DownloadFailedPayload):
        payload = DownloadFailedPayload(**payload)
    media = MediaInfo.model_validate(payload.media_info or {})
    _record_download(
        media,
        LifecycleStage.DOWNLOADING,
        LifecycleStatus.FAILED,
        "download.failed",
        error=payload.reason,
        payload={"source": "DOWNLOAD_FAILED", "reason": payload.reason},
    )
    log.warn(f"[Event]下载失败: {payload.media_info.get('title')} 原因: {payload.reason}")
    publish_download_event(
        {"event": DOWNLOAD_FAILED, "data": {"title": payload.media_info.get("title"), "reason": payload.reason}}
    )


def _parse_season_episode(value: object) -> tuple[int, int]:
    match = re.search(r"S(\d+)\s*E(\d+)", str(value or ""), re.IGNORECASE)
    if not match:
        return 0, 0
    return int(match.group(1)), int(match.group(2))


def _row_media_type(value: object) -> str:
    key = str(value or "").lower()
    return {"mov": "movie", "movie": "movie", "tv": "tv", "ani": "anime", "anime": "anime"}.get(
        key, str(value or "unknown")
    )


@on_event(DOWNLOAD_COMPLETED)
def handle_download_completed(event: Event) -> None:
    """下载完成事件处理器"""
    payload = event.payload
    if not isinstance(payload, DownloadCompletedPayload):
        payload = DownloadCompletedPayload(**payload)
    log.info(f"[Event]下载完成: {payload.task_id} @ {payload.path}")

    try:
        row = DownloadRepository().get_download_history_by_download_id(
            payload.downloader_id or "", payload.task_id or ""
        )
    except Exception as exc:  # noqa: BLE001 - 历史表不可用时仍要转发事件
        log.debug(f"[Lifecycle]读取下载历史失败: {exc}")
        row = None
    if row is not None:
        season, episode = _parse_season_episode(getattr(row, "SE", None))
        resolved = IdentityResolver().resolve_values(
            identity_id=getattr(row, "IDENTITY_ID", None),
            provider=getattr(row, "ANCHOR_PROVIDER", None),
            external_id=getattr(row, "ANCHOR_EXTERNAL_ID", None),
            title=getattr(row, "TITLE", "") or payload.name,
            year=getattr(row, "YEAR", None),
            media_type=_row_media_type(getattr(row, "TYPE", None)),
            content_profile=getattr(row, "CONTENT_PROFILE", None),
            season=season,
            allow_local=True,
        )
        if resolved.identity_id:
            try:
                LifecycleProjector().record(
                    identity_id=resolved.identity_id,
                    stage=LifecycleStage.DOWNLOADED,
                    status=LifecycleStatus.SUCCEEDED,
                    event_type="download.completed",
                    media_type=_row_media_type(getattr(row, "TYPE", None)),
                    season=season,
                    episode=episode,
                    run_id=f"download:{getattr(row, 'ID', payload.task_id)}",
                    trace_id=f"download:{payload.task_id}",
                    title=getattr(row, "TITLE", None),
                    year=getattr(row, "YEAR", None),
                    poster=getattr(row, "POSTER", None),
                    progress=100,
                    source_provider=resolved.provider or getattr(row, "ANCHOR_PROVIDER", None),
                    content_profile=resolved.content_profile or getattr(row, "CONTENT_PROFILE", None),
                    user_id=getattr(row, "USER_ID", None),
                    payload={
                        "downloader_id": payload.downloader_id,
                        "download_id": payload.task_id,
                        "source": "DOWNLOAD_COMPLETED",
                        "path": payload.path,
                    },
                    event_key=f"download-completed:{getattr(row, 'ID', payload.task_id)}:{season}:{episode}",
                )
            except Exception as exc:  # noqa: BLE001
                log.warn(f"[Lifecycle]记录下载完成生命周期失败: {exc}")

    name = payload.name or os.path.basename(str(payload.path or "").rstrip("/")) or payload.task_id
    publish_download_event(
        {
            "event": DOWNLOAD_COMPLETED,
            "data": {
                "downloader_id": payload.downloader_id,
                "task_id": payload.task_id,
                "path": payload.path,
                "tags": payload.tags,
                "name": name,
            },
        }
    )

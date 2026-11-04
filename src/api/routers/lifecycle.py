"""媒体生命周期只读 API（ADR-026）."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.deps import get_downloader_service, require_any_permission, require_permission
from app.db.repositories.lifecycle_repository import (
    LifecycleRepository,
    lifecycle_event_to_dict,
    lifecycle_row_to_dict,
)
from app.schemas.auth import UserContext
from app.services.lifecycle_action_service import LifecycleActionError, LifecycleActionService
from app.services.lifecycle_service import LifecycleReconciler
from app.utils.response import success

router = APIRouter()


def _row_payload(row) -> dict[str, Any]:
    data = dict(row) if isinstance(row, dict) else lifecycle_row_to_dict(row)
    started = data.get("STAGE_STARTED_AT")
    if isinstance(started, str) and started:
        try:
            started = datetime.fromisoformat(started)
        except ValueError:
            started = None
    elapsed = int((datetime.now() - started).total_seconds()) if started else 0
    return {
        "identity_id": data.get("IDENTITY_ID"),
        "media_type": data.get("MEDIA_TYPE"),
        "season": data.get("SEASON"),
        "episode": data.get("EPISODE"),
        "title": data.get("TITLE"),
        "year": data.get("YEAR"),
        "poster": data.get("POSTER"),
        "stage": data.get("STAGE"),
        "status": data.get("STATUS"),
        "run_id": data.get("RUN_ID"),
        "trace_id": data.get("TRACE_ID"),
        "progress": data.get("PROGRESS"),
        "source_provider": data.get("SOURCE_PROVIDER"),
        "content_profile": data.get("CONTENT_PROFILE"),
        "user_id": data.get("USER_ID"),
        "stage_started_at": data.get("STAGE_STARTED_AT"),
        "last_event_at": data.get("LAST_EVENT_AT"),
        "next_retry_at": data.get("NEXT_RETRY_AT"),
        "retry_count": data.get("RETRY_COUNT"),
        "last_error": data.get("LAST_ERROR"),
        "episode_count": data.get("EPISODE_COUNT", 1),
        "completed_episodes": data.get("COMPLETED_EPISODES", 0),
        "in_library_episodes": data.get("IN_LIBRARY_EPISODES", 0),
        "subscribed_episodes": data.get("SUBSCRIBED_EPISODES", 0),
        "missing": bool(data.get("MISSING")),
        "elapsed_seconds": max(0, elapsed),
    }


def _event_payload(row) -> dict[str, Any]:
    data = lifecycle_event_to_dict(row)
    return {
        "id": data.get("ID"),
        "stage": data.get("STAGE"),
        "status": data.get("STATUS"),
        "event_type": data.get("EVENT_TYPE"),
        "message": data.get("MESSAGE"),
        "occurred_at": data.get("OCCURRED_AT"),
        "run_id": data.get("RUN_ID"),
        "trace_id": data.get("TRACE_ID"),
        "payload": data.get("PAYLOAD") or {},
    }


@router.get("", summary="媒体生命周期列表")
def list_lifecycle(
    stage: str | None = Query(default=None),
    status: str | None = Query(default=None),
    media_type: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    pagenum: int = Query(default=20, ge=1, le=100),
    current_user: UserContext = Depends(require_any_permission("library:view", "library:manage")),
):
    rows, total = LifecycleRepository().list_grouped(
        stage=stage,
        status=status,
        media_type=media_type,
        keyword=keyword,
        page=page,
        pagenum=pagenum,
        user=current_user,
    )
    return success(data={"items": [_row_payload(row) for row in rows], "total": total})


@router.post("/reconcile", summary="从历史表回填生命周期")
def reconcile_lifecycle(
    limit: int = Query(default=500, ge=1, le=5000),
    _current_user: UserContext = Depends(require_permission("library:manage")),
):
    return success(data=LifecycleReconciler().reconcile_recent(limit=limit))


@router.get("/stats", summary="媒体生命周期统计")
def lifecycle_stats(
    current_user: UserContext = Depends(require_any_permission("library:view", "library:manage")),
):
    return success(data=LifecycleRepository().stats_grouped(user=current_user))


class IdentifyRequest(BaseModel):
    provider: str
    external_id: str
    title: str | None = None
    year: str | None = None
    poster: str | None = None
    season: int = 0
    episode: int = 0


@router.post("/{identity_id}/retry", summary="重试生命周期任务")
def retry_lifecycle(
    identity_id: str,
    season: int = Query(default=0, ge=0),
    episode: int = Query(default=0, ge=0),
    _current_user: UserContext = Depends(require_permission("library:manage")),
):
    try:
        return success(data=LifecycleActionService().retry(identity_id, season, episode))
    except LifecycleActionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{identity_id}/pause", summary="暂停下载任务")
def pause_lifecycle(
    identity_id: str,
    season: int = Query(default=0, ge=0),
    episode: int = Query(default=0, ge=0),
    downloader: Any = Depends(get_downloader_service),
    _current_user: UserContext = Depends(require_permission("library:manage")),
):
    try:
        return success(data=LifecycleActionService(downloader=downloader).pause(identity_id, season, episode))
    except LifecycleActionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{identity_id}/resume", summary="继续下载任务")
def resume_lifecycle(
    identity_id: str,
    season: int = Query(default=0, ge=0),
    episode: int = Query(default=0, ge=0),
    downloader: Any = Depends(get_downloader_service),
    _current_user: UserContext = Depends(require_permission("library:manage")),
):
    try:
        return success(data=LifecycleActionService(downloader=downloader).resume(identity_id, season, episode))
    except LifecycleActionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{identity_id}/cancel", summary="取消生命周期任务")
def cancel_lifecycle(
    identity_id: str,
    season: int = Query(default=0, ge=0),
    episode: int = Query(default=0, ge=0),
    downloader: Any = Depends(get_downloader_service),
    _current_user: UserContext = Depends(require_permission("library:manage")),
):
    return success(data=LifecycleActionService(downloader=downloader).cancel(identity_id, season, episode))


@router.post("/{identity_id}/identify", summary="手动识别媒体")
def identify_lifecycle(
    identity_id: str,
    payload: IdentifyRequest,
    _current_user: UserContext = Depends(require_permission("library:manage")),
):
    try:
        return success(
            data=LifecycleActionService().identify(
                identity_id,
                provider=payload.provider,
                external_id=payload.external_id,
                title=payload.title,
                year=payload.year,
                poster=payload.poster,
                season=payload.season,
                episode=payload.episode,
            )
        )
    except LifecycleActionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{identity_id}", summary="媒体生命周期详情")
def get_lifecycle(
    identity_id: str,
    season: int = Query(default=0, ge=0),
    episode: int = Query(default=0, ge=0),
    current_user: UserContext = Depends(require_any_permission("library:view", "library:manage")),
):
    repo = LifecycleRepository()
    if season == 0 and episode == 0:
        row = repo.get_grouped_identity(identity_id, user=current_user)
    else:
        row = repo.get_current(identity_id, season=season, episode=episode, user=current_user)
    return success(data=_row_payload(row) if row is not None else None)


@router.get("/{identity_id}/episodes", summary="媒体生命周期季集列表")
def list_lifecycle_episodes(
    identity_id: str,
    current_user: UserContext = Depends(require_any_permission("library:view", "library:manage")),
):
    repo = LifecycleRepository()
    rows = repo.list_identity_rows(identity_id, user=current_user)
    payloads = [_row_payload(row) for row in rows]
    if any(int(item.get("episode") or 0) > 0 for item in payloads):
        payloads = [item for item in payloads if int(item.get("episode") or 0) > 0]
    existing = {(int(item.get("season") or 0), int(item.get("episode") or 0)) for item in payloads}
    first = payloads[0] if payloads else {}
    for summary in repo.list_subscription_summaries(identity_id, user=current_user):
        match = re.search(r"\d+", str(summary.get("season") or ""))
        season = int(match.group()) if match else int(first.get("season") or 0)
        if season <= 0:
            season = 1
        total_ep = int(summary.get("total_ep") or 0)
        if total_ep <= 0:
            continue
        completed_ep = max(0, min(total_ep, int(summary.get("completed_ep") or 0)))
        missing_episodes = {int(item) for item in summary.get("missing_episodes") or []}
        profile = str(summary.get("content_profile") or first.get("content_profile") or "default")
        media_type = "anime" if profile == "anime" else (first.get("media_type") or "tv")
        for episode in range(1, total_ep + 1):
            if (season, episode) in existing:
                continue
            missing = episode in missing_episodes if missing_episodes else episode > completed_ep
            payloads.append(
                _row_payload(
                    {
                        "IDENTITY_ID": identity_id,
                        "MEDIA_TYPE": media_type,
                        "SEASON": season,
                        "EPISODE": episode,
                        "TITLE": first.get("title") or summary.get("name"),
                        "YEAR": first.get("year") or summary.get("year"),
                        "POSTER": first.get("poster"),
                        "STAGE": "subscribed" if missing else "in_library",
                        "STATUS": "queued" if missing else "succeeded",
                        "PROGRESS": 0 if missing else 100,
                        "SOURCE_PROVIDER": first.get("source_provider") or summary.get("anchor_provider"),
                        "CONTENT_PROFILE": profile,
                        "USER_ID": first.get("user_id") or summary.get("user_id"),
                        "EPISODE_COUNT": 1,
                        "COMPLETED_EPISODES": 0 if missing else 1,
                        "IN_LIBRARY_EPISODES": 0 if missing else 1,
                        "MISSING": missing,
                    }
                )
            )
    payloads.sort(key=lambda item: (item.get("season") or 0, item.get("episode") or 0))
    return success(data=payloads)


@router.get("/{identity_id}/events", summary="媒体生命周期时间线")
def list_lifecycle_events(
    identity_id: str,
    season: int = Query(default=0, ge=0),
    episode: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
    current_user: UserContext = Depends(require_any_permission("library:view", "library:manage")),
):
    rows = LifecycleRepository().list_events(
        identity_id, season=season, episode=episode, limit=limit, user=current_user
    )
    return success(data=[_event_payload(row) for row in rows])

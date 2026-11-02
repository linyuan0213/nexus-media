"""媒体生命周期只读 API（ADR-026）."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query

from api.deps import require_any_permission
from app.db.repositories.lifecycle_repository import (
    LifecycleRepository,
    lifecycle_event_to_dict,
    lifecycle_row_to_dict,
)
from app.schemas.auth import UserContext
from app.utils.response import success

router = APIRouter()


def _row_payload(row) -> dict[str, Any]:
    data = lifecycle_row_to_dict(row)
    started = row.STAGE_STARTED_AT or row.LAST_EVENT_AT
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
    rows, total = LifecycleRepository().list_current(
        stage=stage,
        status=status,
        media_type=media_type,
        keyword=keyword,
        page=page,
        pagenum=pagenum,
        user=current_user,
    )
    return success(data={"items": [_row_payload(row) for row in rows], "total": total})


@router.get("/{identity_id}", summary="媒体生命周期详情")
def get_lifecycle(
    identity_id: str,
    season: int = Query(default=0, ge=0),
    episode: int = Query(default=0, ge=0),
    current_user: UserContext = Depends(require_any_permission("library:view", "library:manage")),
):
    row = LifecycleRepository().get_current(
        identity_id, season=season, episode=episode, user=current_user
    )
    return success(data=_row_payload(row) if row is not None else None)


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

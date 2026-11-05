"""规范剧集与来源别名管理 API（不依赖 TMDB）."""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import log
from api.deps import require_permission
from app.db.repositories.media_series_repository import MediaSeriesRepository
from app.schemas.auth import UserContext
from app.utils.response import success

router = APIRouter()


class AliasRequest(BaseModel):
    provider: str
    external_id: str
    scope: str = "default"
    season_number: int = Field(default=1, ge=0, le=999)
    series_key: str


class AliasDeleteRequest(BaseModel):
    provider: str
    external_id: str
    scope: str = "default"
    season_number: int | None = None


class MergeRequest(BaseModel):
    source_key: str
    target_key: str


class SeasonUpdateRequest(BaseModel):
    title: str | None = None
    year: str | None = None
    total_episodes: int | None = Field(default=None, ge=0)
    episode_offset: int | None = None


def _series_dict(row: Any) -> dict:
    return {
        "series_key": row.SERIES_KEY,
        "title": row.TITLE,
        "original_title": row.ORIGINAL_TITLE,
        "year": row.YEAR,
        "total_seasons": row.TOTAL_SEASONS,
        "primary_provider": row.PRIMARY_PROVIDER,
        "primary_external_id": row.PRIMARY_EXTERNAL_ID,
        "created_at": row.CREATED_AT,
        "updated_at": row.UPDATED_AT,
    }


def _season_dict(row: Any) -> dict:
    return {
        "series_key": row.SERIES_KEY,
        "season_number": row.SEASON_NUMBER,
        "title": row.TITLE,
        "year": row.YEAR,
        "total_episodes": row.TOTAL_EPISODES,
        "episode_offset": row.EPISODE_OFFSET,
        "primary_provider": row.PRIMARY_PROVIDER,
        "primary_external_id": row.PRIMARY_EXTERNAL_ID,
    }


def _alias_dict(row: Any) -> dict:
    return {
        "provider": row.PROVIDER,
        "external_id": row.EXTERNAL_ID,
        "scope": row.SCOPE,
        "season_number": row.SEASON_NUMBER,
        "series_key": row.SERIES_KEY,
        "confidence": row.CONFIDENCE,
        "mapping_source": row.MAPPING_SOURCE,
    }


@router.get("")
def list_series(
    search: str | None = None,
    limit: int = 200,
    _user: UserContext = Depends(require_permission("setting:view")),
):
    rows = MediaSeriesRepository().list_series(search=search, limit=min(max(limit, 1), 500))
    return success([_series_dict(row) for row in rows])


@router.get("/{series_key}")
def get_series(
    series_key: str,
    _user: UserContext = Depends(require_permission("setting:view")),
):
    repo = MediaSeriesRepository()
    series = repo.get_series(series_key)
    if series is None:
        return success(None)
    return success(
        {
            **_series_dict(series),
            "seasons": [_season_dict(row) for row in repo.get_seasons(series_key)],
            "aliases": [_alias_dict(row) for row in repo.list_aliases(series_key)],
        }
    )


@router.post("/alias")
def upsert_alias(
    req: AliasRequest,
    _user: UserContext = Depends(require_permission("setting:update")),
):
    repo = MediaSeriesRepository()
    if repo.get_series(req.series_key) is None:
        return success(data=None, message="规范剧集不存在")
    repo.delete_alias(req.provider, req.external_id, req.scope, req.season_number)
    row = repo.create_alias(
        provider=req.provider,
        external_id=req.external_id,
        scope=req.scope,
        season_number=req.season_number,
        series_key=req.series_key,
        confidence=100,
        mapping_source="manual",
    )
    log.info(f"[Series]手动别名 {req.provider}:{req.external_id} -> {req.series_key} S{req.season_number:02d}")
    return success(_alias_dict(row) if row is not None else None)


@router.delete("/alias")
def delete_alias(
    req: AliasDeleteRequest,
    _user: UserContext = Depends(require_permission("setting:update")),
):
    count = MediaSeriesRepository().delete_alias(req.provider, req.external_id, req.scope, req.season_number)
    return success({"deleted": count})


@router.post("/merge")
def merge_series(
    req: MergeRequest,
    _user: UserContext = Depends(require_permission("setting:update")),
):
    ok = MediaSeriesRepository().merge_series(req.source_key, req.target_key)
    if not ok:
        return success(data=None, message="合并失败：源或目标剧集不存在")
    log.info(f"[Series]手动合并 {req.source_key} -> {req.target_key}")
    return success({"merged": True})


@router.patch("/{series_key}/season/{season_number}")
def update_season(
    series_key: str,
    season_number: int,
    req: SeasonUpdateRequest,
    _user: UserContext = Depends(require_permission("setting:update")),
):
    ok = MediaSeriesRepository().update_season(
        series_key,
        season_number,
        TITLE=req.title,
        YEAR=req.year,
        TOTAL_EPISODES=req.total_episodes,
        EPISODE_OFFSET=req.episode_offset,
    )
    return success({"updated": ok})

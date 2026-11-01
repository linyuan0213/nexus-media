"""媒体库批量重命名 API."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from api.deps import get_library_rename_service, require_permission
from app.schemas.auth import UserContext
from app.schemas.common import CommonResponse
from app.utils.response import success

router = APIRouter()


class RenameScopeRequest(BaseModel):
    media_types: list[str] = Field(default_factory=lambda: ["movie", "tv", "anime"])
    roots: list[str] = Field(default_factory=list)
    layout_mode: str = "full"
    preserve_current_category: bool = True
    reorganize_category: bool = False
    use_mediaserver_metadata: bool = True
    allow_online_metadata: bool = False
    reidentify_no_metadata: bool = False
    limit: int = 5000
    server_id: int | None = None


class ManualMetadataRequest(BaseModel):
    backend_id: str = "local"
    path: str
    media_type: str
    title: str | None = None
    year: str | None = None
    tmdbid: str | int | None = None
    metadata_ref: str | None = None
    anchor_provider: str | None = None
    anchor_external_id: str | None = None
    content_profile: str | None = None
    season: int | str | None = None
    episode: int | str | None = None


@router.post(
    "/library/rename/preview",
    response_model=CommonResponse,
    summary="生成媒体库批量重命名预览计划",
)
def preview_rename(
    req: RenameScopeRequest,
    user: UserContext = Depends(require_permission("library:manage")),
    svc=Depends(get_library_rename_service),
):
    return success(data=svc.create_plan(req.model_dump(), user_id=user.user_id))


@router.get(
    "/library/rename/plans/{plan_id}",
    response_model=CommonResponse,
    summary="获取重命名计划",
)
def get_plan(
    plan_id: str,
    user: UserContext = Depends(require_permission("library:manage")),
    svc=Depends(get_library_rename_service),
):
    return success(data=svc.get_plan(plan_id))


@router.get(
    "/library/rename/plans/{plan_id}/items",
    response_model=CommonResponse,
    summary="分页获取重命名计划条目",
)
def list_plan_items(
    plan_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    action: str | None = Query(None),
    user: UserContext = Depends(require_permission("library:manage")),
    svc=Depends(get_library_rename_service),
):
    return success(data=svc.list_items(plan_id, page=page, page_size=page_size, action=action))


@router.post(
    "/library/rename/plans/{plan_id}/execute",
    response_model=CommonResponse,
    summary="执行重命名计划",
)
def execute_plan(
    plan_id: str,
    user: UserContext = Depends(require_permission("library:manage")),
    svc=Depends(get_library_rename_service),
):
    return success(data=svc.execute(plan_id))


@router.get(
    "/library/rename/jobs/{job_id}",
    response_model=CommonResponse,
    summary="获取重命名任务进度",
)
def get_job(
    job_id: int,
    user: UserContext = Depends(require_permission("library:manage")),
    svc=Depends(get_library_rename_service),
):
    return success(data=svc.get_job(job_id))


@router.post(
    "/library/rename/jobs/{job_id}/cancel",
    response_model=CommonResponse,
    summary="取消重命名任务",
)
def cancel_job(
    job_id: int,
    user: UserContext = Depends(require_permission("library:manage")),
    svc=Depends(get_library_rename_service),
):
    return success(data=svc.cancel_job(job_id))


@router.post(
    "/library/rename/jobs/{job_id}/rollback",
    response_model=CommonResponse,
    summary="回滚重命名任务",
)
def rollback_job(
    job_id: int,
    user: UserContext = Depends(require_permission("library:manage")),
    svc=Depends(get_library_rename_service),
):
    return success(data=svc.rollback_job(job_id))


@router.post(
    "/library/metadata",
    response_model=CommonResponse,
    summary="人工补录库内文件元数据",
)
def set_manual_metadata(
    req: ManualMetadataRequest,
    user: UserContext = Depends(require_permission("library:manage")),
    svc=Depends(get_library_rename_service),
):
    return success(
        data=svc.set_manual_metadata(
            backend_id=req.backend_id,
            path=req.path,
            media_type=req.media_type,
            title=req.title,
            year=req.year,
            tmdbid=req.tmdbid,
            metadata_ref=req.metadata_ref,
            anchor_provider=req.anchor_provider,
            anchor_external_id=req.anchor_external_id,
            content_profile=req.content_profile,
            season=req.season,
            episode=req.episode,
            user_id=user.user_id,
        )
    )

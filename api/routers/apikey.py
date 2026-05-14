"""
API Key 管理路由
提供 API Key 的生成、列表、更新、删除和使用记录查询
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.deps import get_current_user
from app.schemas.auth import UserContext
from app.services.apikey_service import APIKeyService
from app.utils.response import success

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic Request/Response Models
# ---------------------------------------------------------------------------

class CreateAPIKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="API Key 名称")
    expires_days: int | None = Field(None, ge=1, le=3650, description="过期天数，null 表示永不过期")
    description: str = Field("", max_length=1000, description="描述")


class UpdateAPIKeyRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    status: int | None = Field(None, ge=0, le=1)
    description: str | None = Field(None, max_length=1000)


class APIKeyResponse(BaseModel):
    id: int
    name: str
    key_prefix: str
    status: int
    expires_at: str | None
    created_at: str | None
    updated_at: str | None
    created_by: int | None
    use_count: int
    last_used_at: str | None
    description: str | None
    is_expired: bool
    is_active: bool


class APIKeyLogResponse(BaseModel):
    id: int
    api_key_id: int
    request_id: str
    request_name: str | None
    source_ip: str | None
    request_path: str | None
    request_method: str | None
    status: int
    response_code: int | None
    error_message: str | None
    request_at: str | None
    response_time_ms: int | None


class CreateAPIKeyResponse(BaseModel):
    id: int
    name: str
    key: str
    prefix: str
    expires_at: str | None
    created_at: str | None
    status: int


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/keys", response_model=success)
async def create_api_key(
    req: CreateAPIKeyRequest,
    user: UserContext = Depends(get_current_user),
):
    """创建新的 API Key"""
    try:
        service = APIKeyService()
        result = service.create_key(
            name=req.name,
            expires_days=req.expires_days,
            description=req.description,
            created_by=user.user_id,
        )
        return success(data=result, message="API Key 创建成功，请妥善保存 Key，此页面为唯一展示机会")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建失败: {str(e)}")


@router.get("/keys", response_model=success)
async def list_api_keys(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: UserContext = Depends(get_current_user),
):
    """获取 API Key 列表"""
    service = APIKeyService()
    result = service.list_keys(page=page, page_size=page_size)
    return success(data=result)


@router.put("/keys/{key_id}", response_model=success)
async def update_api_key(
    key_id: int,
    req: UpdateAPIKeyRequest,
    user: UserContext = Depends(get_current_user),
):
    """更新 API Key"""
    service = APIKeyService()
    ok = service.update_key(
        key_id=key_id,
        name=req.name,
        status=req.status,
        description=req.description,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="API Key 不存在或更新失败")
    return success(message="更新成功")


@router.delete("/keys/{key_id}", response_model=success)
async def delete_api_key(
    key_id: int,
    user: UserContext = Depends(get_current_user),
):
    """删除 API Key"""
    service = APIKeyService()
    ok = service.delete_key(key_id)
    if not ok:
        raise HTTPException(status_code=404, detail="API Key 不存在")
    return success(message="删除成功")


@router.get("/keys/{key_id}/logs", response_model=success)
async def list_api_key_logs(
    key_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: UserContext = Depends(get_current_user),
):
    """获取指定 API Key 的使用记录"""
    service = APIKeyService()
    result = service.list_logs(api_key_id=key_id, page=page, page_size=page_size)
    return success(data=result)


@router.get("/logs", response_model=success)
async def list_all_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: UserContext = Depends(get_current_user),
):
    """获取所有 API Key 的使用记录"""
    service = APIKeyService()
    result = service.list_logs(page=page, page_size=page_size)
    return success(data=result)


@router.get("/stats", response_model=success)
async def get_api_key_stats(
    user: UserContext = Depends(get_current_user),
):
    """获取 API Key 统计信息"""
    service = APIKeyService()
    result = service.get_stats()
    return success(data=result)

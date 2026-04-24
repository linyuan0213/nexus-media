"""
Plugin Router — FastAPI 迁移
对应原 web/controllers/plugin.py，复用 app/services/plugin_service.py
"""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_current_user, get_plugin_service
from app.utils.response import success, fail
from app.services.plugin_service import PluginService

router = APIRouter()


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------

class EmptyRequest(BaseModel):
    data: Optional[dict] = None


class UpdatePluginConfigRequest(BaseModel):
    plugin: Optional[str] = None
    config: Optional[dict] = None


class PluginIdRequest(BaseModel):
    id: Optional[str] = None


class RunPluginMethodRequest(BaseModel):
    plugin_id: Optional[str] = None
    method: Optional[str] = None
    data: Optional[dict] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/update_plugin_config")
def update_plugin_config(
    req: UpdatePluginConfigRequest,
    user: str = Depends(get_current_user),
    svc: PluginService = Depends(get_plugin_service),
):
    plugin_id = req.plugin
    config = req.config or {}
    if not plugin_id:
        return fail(msg="数据错误")
    svc.update_plugin_config(plugin_id=plugin_id, config=config)
    return success(msg="保存成功")


@router.post("/get_plugin_apps")
def get_plugin_apps(
    req: EmptyRequest = EmptyRequest(),
    user: str = Depends(get_current_user),
    svc: PluginService = Depends(get_plugin_service),
):
    # 简化为固定 level=2，与 current_user.level 对应
    dto = svc.get_plugin_apps(user_level=2)
    return success(result=dto.plugins, statistic=dto.statistic)


@router.post("/get_plugin_page")
def get_plugin_page(
    req: PluginIdRequest,
    user: str = Depends(get_current_user),
    svc: PluginService = Depends(get_plugin_service),
):
    plugin_id = req.id
    if not plugin_id:
        return fail(msg="参数错误")
    dto = svc.get_plugin_page(plugin_id)
    return success(title=dto.title, content=dto.content, func=dto.func)


@router.post("/get_plugin_state")
def get_plugin_state(
    req: PluginIdRequest,
    user: str = Depends(get_current_user),
    svc: PluginService = Depends(get_plugin_service),
):
    plugin_id = req.id
    if not plugin_id:
        return fail(msg="参数错误")
    state = svc.get_plugin_state(plugin_id)
    return success(state=state)


@router.post("/get_plugins_conf")
def get_plugins_conf(
    req: EmptyRequest = EmptyRequest(),
    user: str = Depends(get_current_user),
    svc: PluginService = Depends(get_plugin_service),
):
    Plugins = svc.get_plugins_conf(user_level=2)
    return success(result=Plugins)


@router.post("/install_plugin")
def install_plugin(
    req: PluginIdRequest,
    user: str = Depends(get_current_user),
    svc: PluginService = Depends(get_plugin_service),
):
    module_id = req.id
    if not module_id:
        return fail(msg="参数错误")
    dto = svc.install_plugin(module_id)
    if not dto.success:
        return fail(code=-1, msg=dto.msg)
    return success(msg=dto.msg)


@router.post("/run_plugin_method")
def run_plugin_method(
    req: RunPluginMethodRequest,
    user: str = Depends(get_current_user),
    svc: PluginService = Depends(get_plugin_service),
):
    plugin_id = req.plugin_id
    method = req.method
    if not plugin_id or not method:
        return fail(msg="参数错误")
    kwargs = req.data or {}
    result = svc.run_plugin_method(
        plugin_id=plugin_id, method=method, kwargs=kwargs)
    return success(result=result)


@router.post("/uninstall_plugin")
def uninstall_plugin(
    req: PluginIdRequest,
    user: str = Depends(get_current_user),
    svc: PluginService = Depends(get_plugin_service),
):
    module_id = req.id
    dto = svc.uninstall_plugin(module_id)
    if not dto.success:
        return fail(code=-1, msg=dto.msg)
    return success(msg=dto.msg)

"""
Plugin Router — FastAPI 迁移
对应原 web/controllers/plugin.py，复用 app/services/plugin_service.py
"""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_current_user, get_plugin_service, require_any_permission, require_permission
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

@router.post("/plugins/config")
def update_plugin_config(
    req: UpdatePluginConfigRequest,
    user: str = Depends(require_permission("plugin:manage")),
    svc: PluginService = Depends(get_plugin_service),
):
    plugin_id = req.plugin
    config = req.config or {}
    if not plugin_id:
        return fail(msg="数据错误")
    svc.update_plugin_config(plugin_id=plugin_id, config=config)
    return success(msg="保存成功")


@router.post("/plugins/apps")
def get_plugin_apps(
    req: EmptyRequest = EmptyRequest(),
    user: str = Depends(require_any_permission("plugin:view", "plugin:manage")),
    svc: PluginService = Depends(get_plugin_service),
):
    # 简化为固定 level=2，与 current_user.level 对应
    dto = svc.get_plugin_apps(user_level=2)
    return success(data=dto.plugins)


@router.post("/plugins/page")
def get_plugin_page(
    req: PluginIdRequest,
    user: str = Depends(require_any_permission("plugin:view", "plugin:manage")),
    svc: PluginService = Depends(get_plugin_service),
):
    plugin_id = req.id
    if not plugin_id:
        return fail(msg="参数错误")
    dto = svc.get_plugin_page(plugin_id)
    return success(data=dto.title)


@router.post("/plugins/state")
def get_plugin_state(
    req: PluginIdRequest,
    user: str = Depends(require_any_permission("plugin:view", "plugin:manage")),
    svc: PluginService = Depends(get_plugin_service),
):
    plugin_id = req.id
    if not plugin_id:
        return fail(msg="参数错误")
    state = svc.get_plugin_state(plugin_id)
    return success(data=state)


@router.post("/plugins")
def get_plugins_conf(
    req: EmptyRequest = EmptyRequest(),
    user: str = Depends(require_any_permission("plugin:view", "plugin:manage")),
    svc: PluginService = Depends(get_plugin_service),
):
    Plugins = svc.get_plugins_conf(user_level=2)
    return success(data=Plugins)


@router.post("/plugins/install")
def install_plugin(
    req: PluginIdRequest,
    user: str = Depends(require_permission("plugin:manage")),
    svc: PluginService = Depends(get_plugin_service),
):
    module_id = req.id
    if not module_id:
        return fail(msg="参数错误")
    dto = svc.install_plugin(module_id)
    if not dto.success:
        return fail(code=-1, msg=dto.msg)
    return success(msg=dto.msg)


@router.post("/plugins/method")
def run_plugin_method(
    req: RunPluginMethodRequest,
    user: str = Depends(require_permission("plugin:manage")),
    svc: PluginService = Depends(get_plugin_service),
):
    plugin_id = req.plugin_id
    method = req.method
    if not plugin_id or not method:
        return fail(msg="参数错误")
    kwargs = req.data or {}
    result = svc.run_plugin_method(
        plugin_id=plugin_id, method=method, kwargs=kwargs)
    return success(data=result)


@router.post("/plugins/uninstall")
def uninstall_plugin(
    req: PluginIdRequest,
    user: str = Depends(require_permission("plugin:manage")),
    svc: PluginService = Depends(get_plugin_service),
):
    module_id = req.id
    dto = svc.uninstall_plugin(module_id)
    if not dto.success:
        return fail(code=-1, msg=dto.msg)
    return success(msg=dto.msg)

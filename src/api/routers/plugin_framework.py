"""
Plugin Framework Router - FastAPI
插件框架 v2 API 路由
"""

import asyncio
import inspect
import json
import os
import tempfile
import threading
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

import log
from api.deps import (
    get_hook_system,
    get_metadata_service,
    get_plugin_framework_service,
    require_any_permission,
    require_permission,
)
from app.core.error_codes import ErrorCode
from app.core.exceptions import DomainError, NexusError, PermissionDenied, ServiceError
from app.core.settings import settings
from app.plugin_framework import api_registry
from app.plugin_framework.hook_system import HookSystem
from app.schemas.common import CommonResponse
from app.services.metadata_service import MetadataService
from app.services.plugin_framework_service import PluginFrameworkService
from app.utils.response import fail, success

router = APIRouter()


def _assert_private_plugin_access(svc, plugin_id: str, user) -> None:
    """私有插件包配置/数据/API 需要 manifest 声明的权限码."""
    manifest = svc.get_manifest(plugin_id)
    if manifest is None:
        return
    metadata = manifest.backend.metadata
    if getattr(metadata, "visibility", "public") != "private":
        return
    required = getattr(metadata, "required_permission", "") or "metadata:private:view"
    permissions = set(getattr(user, "permissions", []) or [])
    if not getattr(user, "is_superadmin", False) and required not in permissions:
        raise PermissionDenied(f"缺少私有插件权限: {required}")


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------


class PluginIdRequest(BaseModel):
    plugin_id: str


class PluginConfigRequest(BaseModel):
    plugin_id: str
    config: dict


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/plugins", response_model=CommonResponse, summary="列出所有插件")
def list_plugins(
    user: str = Depends(require_any_permission("plugin:view", "plugin:manage")),
    svc: PluginFrameworkService = Depends(get_plugin_framework_service),
):
    """列出所有已安装插件"""
    plugins = svc.list_plugins()
    return success(data=plugins)


@router.get("/plugins/{plugin_id}/manifest", response_model=CommonResponse, summary="获取插件清单")
def get_plugin_manifest(
    plugin_id: str,
    user: str = Depends(require_any_permission("plugin:view", "plugin:manage")),
    svc: PluginFrameworkService = Depends(get_plugin_framework_service),
):
    """获取插件完整 manifest"""
    manifest = svc.get_manifest(plugin_id)
    if not manifest:
        return fail(code=ErrorCode.PLUGIN_NOT_FOUND, msg="插件未找到")
    return success(data=manifest.to_dict())


@router.get("/plugins/{plugin_id}/config", response_model=CommonResponse, summary="获取插件配置")
def get_plugin_config(
    plugin_id: str,
    user: str = Depends(require_any_permission("plugin:view", "plugin:manage")),
    svc: PluginFrameworkService = Depends(get_plugin_framework_service),
):
    """获取插件配置"""
    _assert_private_plugin_access(svc, plugin_id, user)
    config = svc.get_config(plugin_id)
    fields = svc.get_config_fields(plugin_id)
    return success(data={"config": config, "fields": fields})


@router.put("/plugins/{plugin_id}/config", response_model=CommonResponse, summary="保存插件配置")
def save_plugin_config(
    plugin_id: str,
    req: PluginConfigRequest,
    user: str = Depends(require_permission("plugin:manage")),
    svc: PluginFrameworkService = Depends(get_plugin_framework_service),
    metadata_svc: MetadataService = Depends(get_metadata_service),
):
    """保存插件配置"""
    if not svc.get_manifest(plugin_id):
        return fail(code=ErrorCode.PLUGIN_NOT_FOUND, msg="插件未找到")
    _assert_private_plugin_access(svc, plugin_id, user)
    svc.save_config(plugin_id, req.config)
    metadata_svc.bump_detail_cache_version()
    return success(message="保存成功")


@router.post("/plugins/install", response_model=CommonResponse, summary="安装插件")
def install_plugin(
    file: UploadFile = File(...),
    sha256: str | None = Form(None),
    user: str = Depends(require_permission("plugin:manage")),
    svc: PluginFrameworkService = Depends(get_plugin_framework_service),
):
    """安装插件（上传 zip 包）"""
    try:
        suffix = os.path.splitext(file.filename or "")[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(file.file.read())
            tmp_path = tmp.name

        manifest = svc.install(tmp_path, expected_sha256=sha256)
        os.unlink(tmp_path)
        # 详情缓存有 10 分钟 TTL；升级代码不再立即清空全部详情，
        # 避免每次小版本更新后首次打开都重新抓取。
        return success(data={"id": manifest.id, "name": manifest.name}, message="安装成功")
    except (ServiceError, DomainError) as e:
        _code = e.errcode if isinstance(e, NexusError) else ErrorCode.OPERATION_FAILED
        return fail(code=_code, msg=e.message)
    except Exception as e:
        log.error(f"[PluginAPI] 安装插件失败: {e}")
        return fail(msg=f"安装失败: {e!s}")


@router.delete("/plugins/{plugin_id}", response_model=CommonResponse, summary="卸载插件")
def uninstall_plugin(
    plugin_id: str,
    purge_data: bool = False,
    user: str = Depends(require_permission("plugin:manage")),
    svc: PluginFrameworkService = Depends(get_plugin_framework_service),
):
    """卸载插件；默认删除插件私有数据和日志."""
    if not svc.get_manifest(plugin_id):
        return fail(code=ErrorCode.PLUGIN_NOT_FOUND, msg="插件未找到")

    try:
        svc.uninstall(plugin_id, purge_data=purge_data)
        return success(message="卸载成功")
    except (ServiceError, DomainError) as e:
        _code = e.errcode if isinstance(e, NexusError) else ErrorCode.OPERATION_FAILED
        return fail(code=_code, msg=e.message)
    except Exception as e:
        log.error(f"[PluginAPI] 卸载插件失败 {plugin_id}: {e}")
        return fail(msg=f"卸载失败: {e!s}")


@router.post("/plugins/{plugin_id}/enable", response_model=CommonResponse, summary="启用插件")
def enable_plugin(
    plugin_id: str,
    user: str = Depends(require_permission("plugin:manage")),
    svc: PluginFrameworkService = Depends(get_plugin_framework_service),
):
    """启用插件"""
    if not svc.get_manifest(plugin_id):
        return fail(code=ErrorCode.PLUGIN_NOT_FOUND, msg="插件未找到")

    try:
        # 先更新数据库和缓存状态（同步），后台线程加载插件实例
        svc.enable(plugin_id)
        threading.Thread(target=svc._do_enable, args=(plugin_id,), daemon=True).start()
        return success(message="启用中，请稍后刷新")
    except (ServiceError, DomainError) as e:
        _code = e.errcode if isinstance(e, NexusError) else ErrorCode.OPERATION_FAILED
        return fail(code=_code, msg=e.message)
    except Exception as e:
        log.error(f"[PluginAPI] 启用插件失败 {plugin_id}: {e}")
        return fail(msg=f"启用失败: {e!s}")


@router.post("/plugins/{plugin_id}/disable", response_model=CommonResponse, summary="禁用插件")
def disable_plugin(
    plugin_id: str,
    user: str = Depends(require_permission("plugin:manage")),
    svc: PluginFrameworkService = Depends(get_plugin_framework_service),
):
    """禁用插件"""
    if not svc.get_manifest(plugin_id):
        return fail(code=ErrorCode.PLUGIN_NOT_FOUND, msg="插件未找到")

    try:
        svc.disable(plugin_id)
        return success(message="禁用成功")
    except (ServiceError, DomainError) as e:
        _code = e.errcode if isinstance(e, NexusError) else ErrorCode.OPERATION_FAILED
        return fail(code=_code, msg=e.message)
    except Exception as e:
        log.error(f"[PluginAPI] 禁用插件失败 {plugin_id}: {e}")
        return fail(msg=f"禁用失败: {e!s}")


@router.post("/plugins/{plugin_id}/reload", response_model=CommonResponse, summary="重载插件")
def reload_plugin(
    plugin_id: str,
    user: str = Depends(require_permission("plugin:manage")),
    svc: PluginFrameworkService = Depends(get_plugin_framework_service),
):
    """热重载插件"""
    if not svc.get_manifest(plugin_id):
        return fail(code=ErrorCode.PLUGIN_NOT_FOUND, msg="插件未找到")

    try:
        svc.reload_plugin(plugin_id)
        return success(message="重载成功")
    except (ServiceError, DomainError) as e:
        _code = e.errcode if isinstance(e, NexusError) else ErrorCode.OPERATION_FAILED
        return fail(code=_code, msg=e.message)
    except Exception as e:
        log.error(f"[PluginAPI] 重载插件失败 {plugin_id}: {e}")
        return fail(msg=f"重载失败: {e!s}")


@router.post("/plugins/{plugin_id}/run", response_model=CommonResponse, summary="运行插件")
def run_plugin(
    plugin_id: str,
    user: str = Depends(require_permission("plugin:manage")),
    svc: PluginFrameworkService = Depends(get_plugin_framework_service),
):
    """立即运行插件"""
    if not svc.get_manifest(plugin_id):
        return fail(code=ErrorCode.PLUGIN_NOT_FOUND, msg="插件未找到")

    try:
        svc.run_plugin(plugin_id)
        return success(message="运行任务已启动")
    except (ServiceError, DomainError) as e:
        _code = e.errcode if isinstance(e, NexusError) else ErrorCode.OPERATION_FAILED
        return fail(code=_code, msg=e.message)
    except Exception as e:
        log.error(f"[PluginAPI] 运行插件失败 {plugin_id}: {e}")
        return fail(msg=f"运行失败: {e!s}")


def _plugin_api_response(result):
    """把插件 handler 返回值转换为统一响应."""
    if isinstance(result, dict) and "success" in result:
        if result.get("success"):
            return success(data=result.get("data"), message=result.get("message") or "success")
        return fail(msg=result.get("message") or "插件接口调用失败")
    return success(data=result)


_PLUGIN_WRITE_ACTIONS = {
    "apply",
    "create",
    "delete",
    "import",
    "merge",
    "remove",
    "save",
    "sync_tags",
    "update",
}


async def _dispatch_plugin_api(plugin_id: str, api_path: str, params: dict, method: str):
    """在线程池中执行同步 handler；async handler 直接 await."""
    if method == "GET" and str(params.get("action") or "").strip().lower() in _PLUGIN_WRITE_ACTIONS:
        return fail(code=ErrorCode.PERMISSION_DENIED, msg="写操作只允许 POST")
    handler = api_registry.get_api_handler(plugin_id, api_path, method)
    if not handler:
        return fail(msg=f"插件接口不存在: {api_path}")
    try:
        if inspect.iscoroutinefunction(handler):
            result = await handler(params)
        else:
            result = await run_in_threadpool(handler, params)
            if inspect.isawaitable(result):
                result = await result
        return _plugin_api_response(result)
    except (ServiceError, DomainError) as e:
        _code = e.errcode if isinstance(e, NexusError) else ErrorCode.OPERATION_FAILED
        return fail(code=_code, msg=e.message)
    except Exception as e:
        log.error(f"[PluginAPI] 插件接口异常 {plugin_id}/{api_path}: {e}")
        return fail(msg=f"插件接口异常: {e!s}")


_MAX_PLUGIN_API_BODY = 8 * 1024 * 1024


@router.get("/plugins/{plugin_id}/api/{api_path:path}", response_model=CommonResponse, summary="插件自定义接口GET")
async def plugin_api_get(
    plugin_id: str,
    api_path: str,
    request: Request,
    user: str = Depends(require_permission("plugin:view")),
    svc: PluginFrameworkService = Depends(get_plugin_framework_service),
):
    _assert_private_plugin_access(svc, plugin_id, user)
    return await _dispatch_plugin_api(plugin_id, api_path, dict(request.query_params), "GET")


@router.post("/plugins/{plugin_id}/api/{api_path:path}", response_model=CommonResponse, summary="插件自定义接口POST")
async def plugin_api_post(
    plugin_id: str,
    api_path: str,
    request: Request,
    user: str = Depends(require_permission("plugin:manage")),
    svc: PluginFrameworkService = Depends(get_plugin_framework_service),
):
    _assert_private_plugin_access(svc, plugin_id, user)
    params: dict = dict(request.query_params)
    try:
        content_length = request.headers.get("content-length")
        try:
            too_large = bool(content_length) and int(content_length) > _MAX_PLUGIN_API_BODY
        except ValueError:
            too_large = False
        if too_large:
            return fail(code=ErrorCode.PARAM_VALIDATION_FAILED, msg="请求体过大")
        body = await request.json()
        if isinstance(body, dict):
            params.update(body)
    except Exception as e:
        log.debug(f"[PluginAPI] 请求体非 JSON，忽略: {e}")
    return await _dispatch_plugin_api(plugin_id, api_path, params, "POST")


@router.get("/plugins/{plugin_id}/logs", response_model=CommonResponse, summary="获取插件日志")
def get_plugin_logs(
    plugin_id: str,
    page: int = 1,
    page_size: int = 20,
    user: str = Depends(require_any_permission("plugin:view", "plugin:manage")),
    svc: PluginFrameworkService = Depends(get_plugin_framework_service),
):
    """获取插件日志"""
    _assert_private_plugin_access(svc, plugin_id, user)
    result = svc.get_logs(plugin_id, page, page_size)
    return success(data=result)


@router.delete("/plugins/{plugin_id}/logs", response_model=CommonResponse, summary="清空插件日志")
def clear_plugin_logs(
    plugin_id: str,
    user: str = Depends(require_permission("plugin:manage")),
    svc: PluginFrameworkService = Depends(get_plugin_framework_service),
):
    """清空插件日志"""
    svc.clear_logs(plugin_id)
    return success(message="日志已清空")


@router.get("/plugins/{plugin_id}/readme", response_model=CommonResponse, summary="获取插件 README")
def get_plugin_readme(
    plugin_id: str,
    user: str = Depends(require_any_permission("plugin:view", "plugin:manage")),
    svc: PluginFrameworkService = Depends(get_plugin_framework_service),
):
    """获取插件 README"""
    _assert_private_plugin_access(svc, plugin_id, user)
    content = svc.get_readme(plugin_id)
    return success(data=content)


@router.get("/hooks/events")
def list_hook_events(
    user: str = Depends(require_any_permission("plugin:view", "plugin:manage")),
    hook_system: HookSystem = Depends(get_hook_system),
):
    """列出所有可用事件"""
    return success(data=hook_system.EVENTS)


@router.get("/plugins/{plugin_id}/data/{filename}")
def get_plugin_data(
    plugin_id: str,
    filename: str,
    user: str = Depends(require_any_permission("plugin:view", "plugin:manage")),
    svc: PluginFrameworkService = Depends(get_plugin_framework_service),
):
    """获取插件数据文件（JSON）"""
    _assert_private_plugin_access(svc, plugin_id, user)
    try:
        data_dir = os.path.join(settings.data_path, "plugins_data", plugin_id)
        target = os.path.join(data_dir, filename)
        real_dir = os.path.realpath(data_dir)
        real_target = os.path.realpath(target)
        if os.path.commonpath([real_dir, real_target]) != real_dir:
            return fail(code=ErrorCode.PARAM_VALIDATION_FAILED, msg="非法路径")
        if not os.path.exists(target):
            return success(data=[])
        with open(target, encoding="utf-8") as f:
            data = json.load(f)
        # 如果是字典，返回 values 列表
        if isinstance(data, dict):
            return success(data=list(data.values()))
        return success(data=data)
    except (ServiceError, DomainError) as e:
        _code = e.errcode if isinstance(e, NexusError) else ErrorCode.OPERATION_FAILED
        return fail(code=_code, msg=e.message)
    except Exception as e:
        log.error(f"[PluginAPI] 获取插件数据失败: {e}")
        return fail(msg=f"获取数据失败: {e!s}")


@router.delete("/plugins/{plugin_id}/data/{filename}/{item_id}")
def delete_plugin_data(
    plugin_id: str,
    filename: str,
    item_id: str,
    user: str = Depends(require_permission("plugin:manage")),
    svc: PluginFrameworkService = Depends(get_plugin_framework_service),
):
    """删除插件数据文件中的某条记录"""
    _assert_private_plugin_access(svc, plugin_id, user)
    try:
        data_dir = os.path.join(settings.data_path, "plugins_data", plugin_id)
        target = os.path.join(data_dir, filename)
        real_dir = os.path.realpath(data_dir)
        real_target = os.path.realpath(target)
        if os.path.commonpath([real_dir, real_target]) != real_dir:
            return fail(code=ErrorCode.PARAM_VALIDATION_FAILED, msg="非法路径")
        if not os.path.exists(target):
            return fail(code=ErrorCode.RESOURCE_NOT_FOUND, msg="数据文件不存在")
        with open(target, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and item_id in data:
            del data[item_id]
        elif isinstance(data, list):
            data = [x for x in data if str(x.get("id", x)) != item_id]
        else:
            return fail(code=ErrorCode.RESOURCE_NOT_FOUND, msg="记录不存在")
        with open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return success(message="删除成功")
    except (ServiceError, DomainError) as e:
        _code = e.errcode if isinstance(e, NexusError) else ErrorCode.OPERATION_FAILED
        return fail(code=_code, msg=e.message)
    except Exception as e:
        log.error(f"[PluginAPI] 删除插件数据失败: {e}")
        return fail(msg=f"删除失败: {e!s}")


@router.get("/plugins/{plugin_id}/assets/{file_path:path}")
def get_plugin_asset(
    plugin_id: str,
    file_path: str,
    svc: PluginFrameworkService = Depends(get_plugin_framework_service),
):
    """获取插件前端资源文件（ESM 组件等）.

    URL 中的 /assets/ 前缀映射到插件根目录；
    若插件未提供前端资源，返回空 JS 占位，避免前端 loader 报 404.
    """
    plugin_path = svc.get_plugin_path(plugin_id)
    if not plugin_path:
        return fail(code=ErrorCode.PLUGIN_NOT_FOUND, msg="插件未找到")

    # /assets/ 是虚拟前缀；仅暴露 frontend/ 前端构建产物，禁止读取后端源码。
    relative_path = file_path
    if relative_path.startswith("assets/"):
        relative_path = relative_path[len("assets/") :]
    relative_posix = relative_path.replace("\\", "/")
    safe_suffixes = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".ico"}
    is_frontend = relative_posix.startswith("frontend/")
    is_public_image = (
        not relative_posix.startswith("backend/") and os.path.splitext(relative_posix)[1].lower() in safe_suffixes
    )
    if not (is_frontend or is_public_image):
        return fail(code=ErrorCode.RESOURCE_NOT_FOUND, msg="资源不存在")

    target = os.path.join(plugin_path, relative_path)
    real_plugin_path = os.path.realpath(plugin_path)
    real_target = os.path.realpath(target)

    # 路径必须严格位于本插件目录内：用 commonpath 而非字符串前缀，
    # 防止 /plugins/foo 前缀匹配到 /plugins/foobar，或 ../ 逃逸
    try:
        if os.path.commonpath([real_plugin_path, real_target]) != real_plugin_path:
            return fail(code=ErrorCode.PARAM_VALIDATION_FAILED, msg="非法路径")
    except ValueError:
        return fail(code=ErrorCode.PARAM_VALIDATION_FAILED, msg="非法路径")

    if not os.path.exists(target) or not os.path.isfile(target):
        if relative_path.endswith("index.mjs"):
            empty_esm = "export default {};\n"
            return Response(
                content=empty_esm,
                media_type="application/javascript",
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )
        return fail(code=ErrorCode.RESOURCE_NOT_FOUND, msg="文件不存在")

    return FileResponse(
        target,
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


_MAX_CALLBACK_BODY = 1 * 1024 * 1024


@router.post("/webhooks/{plugin_id}/{webhook_path:path}", summary="插件公开回调")
async def plugin_public_webhook(plugin_id: str, webhook_path: str, request: Request):
    """插件公开回调（免鉴权），供飞书/Telegram 等外部平台 webhook 回调.

    处理器由插件通过 PluginContext.register_public_webhook(path, handler) 注册，
    约定 handler(params: dict) -> dict。来源校验由插件回调内自行完成（如 apikey）。
    query 参数与 JSON body 合并后一并传入 handler。
    """
    handler = api_registry.get_webhook_handler(plugin_id, webhook_path)
    if not handler:
        return _webhook_response({"code": -1, "msg": "回调接口不存在"})
    # 先按 Content-Length 预检，再流式读取累计，超限即中断（防大 body 内存 DoS）
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > _MAX_CALLBACK_BODY:
                return _webhook_response({"code": -1, "msg": "请求体过大"})
        except ValueError:
            pass
    chunks = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > _MAX_CALLBACK_BODY:
            return _webhook_response({"code": -1, "msg": "请求体过大"})
        chunks.append(chunk)
    raw = b"".join(chunks)
    params: dict = dict(request.query_params)
    if raw:
        try:
            body = json.loads(raw)
            if isinstance(body, dict):
                params.update(body)
        except ValueError:
            pass
    # _client_ip 为真实来源 IP，禁止被 query/body 覆盖（防伪造绕过白名单）
    params.pop("_client_ip", None)
    params["_client_ip"] = request.client.host if request.client else ""
    try:
        if inspect.iscoroutinefunction(handler):
            result = await handler(params)
        else:
            result = await asyncio.to_thread(handler, params)
    except Exception as e:
        log.error(f"[PluginAPI] 插件回调异常 {plugin_id}/{webhook_path}: {e}")
        return _webhook_response({"code": -1, "msg": f"回调处理异常: {e!s}"})
    if result is None:
        result = {"code": 0, "msg": "success"}
    return _webhook_response(result)


def _webhook_response(data: Any) -> Response:
    """构造插件回调 JSON 响应"""
    return Response(content=json.dumps(data, ensure_ascii=False), media_type="application/json")

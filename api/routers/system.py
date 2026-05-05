"""
System Router — FastAPI 迁移
对应原 web/controllers/system.py，复用 app/services/system_service.py
"""
import datetime
import json
import platform

import log
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.deps import (
    get_current_user,
    require_any_permission,
    require_permission,
    get_config_service,
    get_message_service,
    get_net_test_service,
    get_backup_restore_service,
    get_indexer_config_service,
    get_media_server_config_service,
    get_system_scheduler_service,
    get_web_search_service,
    get_system_config_service,
    get_config_update_service,
    get_user_manage_service,
    get_version_service,
    get_progress_service,
    get_message_sender_service,
    get_indexer_service,
    get_system_info_service,
)
from app.utils.response import success, fail
from app.services.system_service import (
    MessageClientService,
    BackupRestoreService,
    IndexerConfigService,
    MediaServerConfigService,
    NetTestService,
    SchedulerService,
    WebSearchService,
    SystemConfigService,
    VersionService,
    MessageSenderService,
    ProgressService,
    UserManageService,
    ConfigUpdateService,
    SystemInfoService,
)
from app.db.repositories import ConfigRepository
from app.schemas.auth import UserContext
from app.utils import ExceptionUtils
from app.services.system_service import restart_server
from app.services.indexer_service import IndexerService
from app.conf import ModuleConf
from app.conf.systemconfig import SystemConfig
from app.utils.types import SystemConfigKey

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic Request Models
# ---------------------------------------------------------------------------

class EmptyRequest(BaseModel):
    """兼容前端 payload 中无 data 字段或 data 为空的情况"""
    data: Optional[dict] = None


class MessageClientRequest(BaseModel):
    flag: Optional[str] = None
    cid: Optional[int] = None
    type: Optional[str] = None
    checked: Optional[bool] = None
    name: Optional[str] = None
    config: Optional[str] = None
    switchs: Optional[str] = None
    interactive: Optional[int] = None
    enabled: Optional[int] = None
    templates: Optional[str] = None


class NetTestRequest(BaseModel):
    target: Optional[str] = None


class IndexerConfigRequest(BaseModel):
    data: dict


class MediaServerConfigRequest(BaseModel):
    data: dict


class SchedulerRequest(BaseModel):
    item: Optional[str] = None


class SearchRequest(BaseModel):
    search_word: Optional[str] = None
    unident: Optional[bool] = None
    filters: Optional[dict] = None
    tmdbid: Optional[str] = None
    media_type: Optional[str] = None


class SystemConfigRequest(BaseModel):
    key: Optional[str] = None
    value: Optional[str] = None


class TestMessageClientRequest(BaseModel):
    type: Optional[str] = None
    config: Optional[str] = None


class UpdateAllConfigRequest(BaseModel):
    conf: Optional[dict] = None
    db: Optional[dict] = None
    test: Optional[bool] = None


class UpdateConfigRequest(BaseModel):
    data: dict


class BackupRequest(BaseModel):
    file_name: Optional[str] = None


class UserManagerRequest(BaseModel):
    oper: Optional[str] = None
    name: Optional[str] = None
    password: Optional[str] = None
    pris: Optional[str] = None


class ProgressRequest(BaseModel):
    type: Optional[str] = None


class SendCustomMessageRequest(BaseModel):
    message_clients: Optional[list] = None
    title: Optional[str] = None
    text: Optional[str] = None
    image: Optional[str] = None


class SendPluginMessageRequest(BaseModel):
    title: Optional[str] = None
    text: Optional[str] = None
    image: Optional[str] = None


# ---------------------------------------------------------------------------
# 辅助函数：统一从 payload 中提取 data
# ---------------------------------------------------------------------------

def _extract_data(payload: BaseModel) -> dict:
    """从 Pydantic 模型中提取 data 字段，若不存在则返回模型本身的 dict"""
    d = payload.model_dump()
    if "data" in d and d["data"] is not None:
        return d["data"]
    return d


# ---------------------------------------------------------------------------
# Router Endpoints
# ---------------------------------------------------------------------------

@router.post("/info")
def system_info(
    current_user: UserContext = Depends(require_any_permission("setting:view", "setting:update")),
    svc: SystemInfoService = Depends(get_system_info_service),
):
    """获取系统基本信息（版本、运行时长、Python版本等）"""
    info = svc.get_system_info()
    return success(data={
        "version": info.version,
        "python_version": info.python_version,
        "platform": info.platform,
        "uptime": info.uptime,
        "uptime_seconds": info.uptime_seconds,
        "start_time": info.start_time,
        "memory_mb": info.memory_mb,
    })


@router.post("/check_message_client")
def check_message_client(
    req: MessageClientRequest,
    current_user: UserContext = Depends(require_any_permission("setting:view", "setting:update")),
    svc: MessageClientService = Depends(get_message_service),
):
    flag = req.flag
    if flag == "interactive":
        svc.toggle_interactive(cid=req.cid, ctype=req.type, checked=req.checked)
        return success()
    elif flag == "enable":
        svc.toggle_enable(cid=req.cid, checked=req.checked)
        return success()
    else:
        return fail()


@router.post("/message_clients/delete")
def delete_message_client(
    req: MessageClientRequest,
    current_user: UserContext = Depends(require_permission("setting:update")),
    svc: MessageClientService = Depends(get_message_service),
):
    if svc.delete_client(cid=req.cid):
        return success()
    else:
        return fail()

@router.post("/message_clients")
def get_message_client(
    req: MessageClientRequest,
    current_user: UserContext = Depends(require_permission("setting:update")),
    svc: MessageClientService = Depends(get_message_service),
):
    data = svc.get_client(cid=req.cid)
    # 热修复：确保 switchs 始终是列表（兼容旧脏数据）
    all_switch_keys = set(ModuleConf.MESSAGE_CONF.get("switch", {}).keys())
    if isinstance(data, dict):
        for client in data.values():
            switchs = client.get("switchs")
            if isinstance(switchs, str):
                client["switchs"] = [s.strip() for s in switchs.split(",") if s.strip() and s.strip() in all_switch_keys]
            elif not isinstance(switchs, list):
                client["switchs"] = []
    return success(data=data)


@router.post("/message_clients/config")
def get_message_client_config(
    current_user: UserContext = Depends(require_permission("setting:update")),
):
    """获取消息通知配置模板（channels + switchs），field.id 统一为 config key"""
    conf = ModuleConf.MESSAGE_CONF
    clients = {}
    for key, item in conf.get("client", {}).items():
        # 将 config 中 field.id 统一为 config 的 key（与数据库保持一致）
        config_fields = {}
        for field_key, field in item.get("config", {}).items():
            field_copy = dict(field)
            field_copy["id"] = field_key
            config_fields[field_key] = field_copy
        clients[key] = {
            "name": item.get("name"),
            "img_url": item.get("img_url", "").replace("../", "/").replace("./", "/"),
            "color": item.get("color", ""),
            "search_type": item.get("search_type"),
            "max_length": item.get("max_length"),
            "config": config_fields,
        }
    switchs = {}
    for key, item in conf.get("switch", {}).items():
        switchs[key] = {
            "name": item.get("name"),
            "fuc_name": item.get("fuc_name"),
        }
    return success(data={
        "channels": clients,
        "switchs": switchs,
    })



@router.post("/net_test")
def net_test(
    req: NetTestRequest,
    current_user: UserContext = Depends(require_any_permission("setting:view", "setting:update")),
    svc = Depends(get_net_test_service),
):
    result = svc.test(target=req.target or "")
    return success(data={"res": result.success, "time": "%s 毫秒" % result.time_ms})


@router.post("/db/reset_version")
def reset_db_version(
    req: EmptyRequest = EmptyRequest(),
    current_user: UserContext = Depends(require_permission("setting:update")),
):
    try:
        ConfigRepository().drop_table("alembic_version")
        return success()
    except Exception as e:
        ExceptionUtils.exception_traceback(e)
        return fail(msg=str(e))


@router.post("/restart")
def restart(
    req: EmptyRequest = EmptyRequest(),
    current_user: UserContext = Depends(require_permission("setting:update")),
):
    restart_server()
    return success()


@router.post("/backup")
def backup(
    current_user: UserContext = Depends(require_permission("setting:update")),
):
    """备份配置文件"""
    from app.services.system_service import backup as do_backup
    import os
    from fastapi.responses import FileResponse
    zip_file = do_backup()
    if not zip_file:
        return fail(msg="创建备份失败")
    return FileResponse(zip_file, filename=os.path.basename(zip_file))


@router.post("/backup/upload")
async def backup_upload(
    file: UploadFile = File(...),
    current_user: UserContext = Depends(require_permission("setting:update")),
):
    """上传备份文件"""
    from pathlib import Path
    from app.utils.temp_manager import temp_manager
    try:
        file_path = Path(temp_manager.get_temp_path()) / file.filename
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)
        return success(data={"filepath": str(file_path)})
    except Exception as e:
        return fail(msg=str(e))


@router.post("/backup/restore")
def restory_backup(
    req: BackupRequest,
    current_user: UserContext = Depends(require_permission("setting:update")),
    svc = Depends(get_backup_restore_service),
):
    filename = req.file_name
    result = svc.restore_from_backup(filename)
    if result.success:
        return success(data=[], msg=result.message)
    return fail(msg=result.message)


@router.post("/indexers")
def get_indexers(
    current_user: UserContext = Depends(require_permission("setting:update")),
    idx_svc: IndexerService = Depends(get_indexer_service),
):
    """获取索引器配置信息（外部索引器配置、内置站点列表、当前配置）"""
    from app.utils.types import SystemConfigKey
    indexers = idx_svc.get_builtin_indexers(check=False)
    private_count = len([item.id for item in indexers if not item.public])
    public_count = len([item.id for item in indexers if item.public])
    indexer_sites = SystemConfig().get(SystemConfigKey.UserIndexerSites) or []
    search_indexer = SystemConfig().get(SystemConfigKey.SearchIndexer) or 'builtin'
    indexer_config = SystemConfig().get(SystemConfigKey.IndexerConfig) or {}
    return success(data={
        "indexers": indexers,
        "private_count": private_count,
        "public_count": public_count,
        "indexer_conf": ModuleConf.INDEXER_CONF,
        "indexer_sites": indexer_sites,
        "search_indexer": search_indexer,
        "indexer_config": indexer_config,
    })


@router.post("/indexers/test")
def test_indexer(
    req: IndexerConfigRequest,
    current_user: UserContext = Depends(require_permission("setting:update")),
    svc = Depends(get_indexer_config_service),
):
    """测试索引器连接"""
    data = dict(req.data)
    data["test"] = True
    result = svc.save_config(data)
    if result.success:
        if result.code == 0:
            return success(msg=result.msg)
        return fail(code=result.code, msg=result.msg)
    return fail(code=result.code, msg=result.msg)


@router.post("/indexers/config")
def save_indexer_config(
    req: IndexerConfigRequest,
    current_user: UserContext = Depends(require_permission("setting:update")),
    svc = Depends(get_indexer_config_service),
):
    result = svc.save_config(req.data)
    if result.success and result.code == 0:
        return success()
    return fail(code=result.code, msg=result.msg)


@router.post("/mediaservers")
def get_mediaservers(
    current_user: UserContext = Depends(require_permission("setting:update")),
):
    """获取媒体服务器配置信息"""
    from app.db.repositories.config_repo_adapter import MediaServerRepositoryAdapter
    repo = MediaServerRepositoryAdapter()
    servers = repo.get_media_servers()
    default_server = repo.get_default_media_server()
    server_dict = {}
    for item in servers:
        try:
            cfg = json.loads(item.CONFIG) if item.CONFIG else {}
        except json.JSONDecodeError:
            cfg = {}
        server_dict[item.NAME] = {
            "id": item.ID,
            "name": item.NAME,
            "enabled": item.ENABLED,
            "is_default": item.IS_DEFAULT,
            "config": cfg,
        }
    return success(data={
        "servers": server_dict,
        "default_server": default_server.NAME if default_server else None,
        "mediaserver_conf": ModuleConf.MEDIASERVER_CONF,
    })


@router.post("/mediaservers/test")
def test_mediaserver(
    req: MediaServerConfigRequest,
    current_user: UserContext = Depends(require_permission("setting:update")),
    svc = Depends(get_media_server_config_service),
):
    """测试媒体服务器连接"""
    data = dict(req.data)
    data["test"] = True
    result = svc.save_config(data)
    if result.success:
        if result.code == 0:
            return success(msg=result.msg)
        return fail(code=result.code, msg=result.msg)
    return fail(code=result.code, msg=result.msg)


@router.post("/mediaservers/config")
def save_mediaserver_config(
    req: MediaServerConfigRequest,
    current_user: UserContext = Depends(require_permission("setting:update")),
    svc = Depends(get_media_server_config_service),
):
    result = svc.save_config(req.data)
    if result.success and result.code == 0:
        return success()
    return fail(code=result.code, msg=result.msg)


@router.post("/scheduler/run")
def sch(
    req: SchedulerRequest,
    current_user: UserContext = Depends(require_permission("setting:update")),
    svc = Depends(get_system_scheduler_service),
):
    ok, msg = svc.start_service(item=req.item)
    if ok:
        return success(data={"msg":msg, "item":req.item})
    return success(data={"msg":msg, "item":req.item})


@router.post("/search")
def search(
    req: SearchRequest,
    current_user: UserContext = Depends(require_any_permission("setting:view", "setting:update")),
    svc = Depends(get_web_search_service),
):
    """
    WEB资源搜索（同步执行，前端并行轮询进度）
    """
    try:
        from app.utils import TokenCache
        TokenCache.delete("search")
    except Exception:
        pass
    search_word = req.search_word
    ident_flag = False if req.unident else True
    result = svc.search(
        search_word=search_word, ident_flag=ident_flag,
        filters=req.filters, tmdbid=req.tmdbid, media_type=req.media_type
    )
    if result.code != 0:
        return fail(code=result.code, msg=result.msg)
    return success()


def _flatten_config(cfg: dict, prefix: str = "") -> dict:
    """将嵌套配置字典扁平化为 dot-notation 键值对"""
    result = {}
    for key, value in cfg.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            result.update(_flatten_config(value, full_key))
        else:
            result[full_key] = value
    return result


@router.post("/config")
def set_system_config(
    req: SystemConfigRequest,
    current_user: UserContext = Depends(require_permission("setting:update")),
    svc = Depends(get_system_config_service),
):
    if svc.set_config(req.key, req.value):
        return success()
    return fail()


@router.post("/config/all")
def get_all_config(
    current_user: UserContext = Depends(require_any_permission("setting:view", "setting:update")),
    svc = Depends(get_config_service),
):
    """获取所有系统配置（扁平化，供基础设置页面使用）"""
    cfg = svc.get_config() or {}
    flat = _flatten_config(cfg)
    # 代理特殊处理：显示 http 代理地址
    proxies = cfg.get("app", {}).get("proxies", {})
    http_proxy = proxies.get("http") if isinstance(proxies, dict) else None
    if http_proxy:
        flat["app.proxies"] = http_proxy.replace("http://", "")
    return success(data=flat)


@router.post("/message_clients/test")
def test_message_client(
    req: TestMessageClientRequest,
    current_user: UserContext = Depends(require_permission("setting:update")),
    svc: MessageClientService = Depends(get_message_service),
):
    import json
    config = json.loads(req.config) if req.config else {}
    if svc.test_connection(ctype=req.type, config=config):
        return success()
    else:
        return fail()



@router.post("/config/update")
def update_config(
    req: UpdateConfigRequest,
    current_user: UserContext = Depends(require_permission("setting:update")),
    svc = Depends(get_config_update_service),
):
    result = svc.update_config(req.data)
    if result.success:
        return success()
    return fail()


@router.post("/message_clients/update")
def update_message_client(
    req: MessageClientRequest,
    current_user: UserContext = Depends(require_permission("setting:update")),
    svc: MessageClientService = Depends(get_message_service),
):
    svc.upsert_client(
        name=req.name,
        cid=req.cid,
        ctype=req.type,
        config=req.config,
        switchs=req.switchs,
        interactive=req.interactive,
        enabled=req.enabled,
        templates=req.templates,
    )
    return success()


@router.post("/users/legacy")
def user_manager(
    req: UserManagerRequest,
    current_user: UserContext = Depends(require_permission("setting:update")),
    svc = Depends(get_user_manage_service),
):
    from app.utils.security import generate_password_hash
    oper = req.oper
    name = req.name
    if oper == "add":
        password = generate_password_hash(str(req.password))
        result = svc.add_user(name=name, password=password)
    else:
        result = svc.delete_user(name=name)

    if result.success:
        return success(data={"success":False})
    return fail(code=-1, success=False, message=result.message or '操作失败')


@router.post("/commands")
def system_commands(
    current_user: UserContext = Depends(require_any_permission("setting:view", "setting:update")),
):
    """获取系统命令列表"""
    from app.services.system_service import get_commands
    cmds = get_commands()
    return success(data=cmds)


@router.post("/status")
def system_status(
    req: EmptyRequest = EmptyRequest(),
    current_user: UserContext = Depends(require_any_permission("setting:view", "setting:update")),
    info_svc = Depends(get_system_info_service),
):
    info = info_svc.get_system_info()
    return success(data={
        "version": info.version,
        "uptime": info.uptime_seconds,
        "python_version": info.python_version,
    })


@router.post("/refresh")
def refresh_process(
    req: ProgressRequest,
    user: str = Depends(require_any_permission("setting:view", "setting:update")),
    svc = Depends(get_progress_service),
):
    result = svc.get_progress(ptype=req.type)
    return success(data={"value": result.value, "text": result.text or "正在处理..."})


@router.post("/messages/send")
def send_custom_message(
    req: SendCustomMessageRequest,
    user: str = Depends(require_permission("setting:update")),
    svc: MessageSenderService = Depends(get_message_sender_service),
):
    result = svc.send_custom_message(
        clients=req.message_clients,
        title=req.title,
        text=req.text or "",
        image=req.image or "",
    )
    if result.success:
        return success()
    return fail(msg=result.message)


@router.post("/messages/send_plugin")
def send_plugin_message(
    req: SendPluginMessageRequest,
    user: str = Depends(require_permission("setting:update")),
    svc: MessageSenderService = Depends(get_message_sender_service)
):
    svc.send_plugin_message(
        title=req.title,
        text=req.text or "",
        image=req.image or "",
    )
    return success()



class LogsRequest(BaseModel):
    source: Optional[str] = None
    level: Optional[str] = None
    limit: Optional[int] = 200


@router.post("/logs")
def get_logs(
    req: LogsRequest,
    user: str = Depends(require_permission("log:view")),
):
    from log import LOG_BUFFER
    logs, _ = LOG_BUFFER.get_logs(source=req.source)
    if req.level:
        logs = [lg for lg in logs if lg.get("level") == req.level]
    if req.limit and req.limit > 0:
        logs = logs[-req.limit:]
    return success(data=logs)


@router.post("/processes")
def processes(
    req: EmptyRequest = EmptyRequest(),
    user: str = Depends(require_any_permission("setting:view", "setting:update")),
):
    from app.utils.system_utils import SystemUtils
    return success(data=SystemUtils.get_all_processes())


# ---------------------------------------------------------------------------
# 日志流 (SSE)
# ---------------------------------------------------------------------------

@router.get("/stream-logging")
def stream_logging(
    request: Request,
    source: Optional[str] = Query(""),
    token: Optional[str] = Query(""),
):
    """实时日志 EventSource 响应
    兼容 EventSource 无法携带自定义 Header 的限制，支持从 query param 传入 token。
    """
    from app.services.auth_service import AuthService
    from api.deps import _extract_user_ctx_from_session
    from app.services.log_streaming_service import LogStreamingService

    # 认证：优先 query param token，其次 session
    user_ctx = None
    if token:
        user_ctx = AuthService.verify_token(token)
    if not user_ctx:
        user_ctx = _extract_user_ctx_from_session(request)
    if not user_ctx:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证失败，请检查登录状态或 Token",
        )

    # 权限检查
    if not user_ctx.is_superadmin and "log:view" not in user_ctx.permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足，需要日志查看权限",
        )

    log_streaming_service = LogStreamingService(sleep_interval=0.3)
    return StreamingResponse(
        log_streaming_service.stream(source or ""),
        media_type="text/event-stream"
    )

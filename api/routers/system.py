"""
System Router — FastAPI 迁移
对应原 web/controllers/system.py，复用 app/services/system_service.py
"""
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from api.deps import (
    get_current_user,
    get_message_service,
    get_net_test_service,
    get_backup_restore_service,
    get_indexer_config_service,
    get_media_server_config_service,
    get_scheduler_service,
    get_web_search_service,
    get_system_config_service,
    get_config_update_service,
    get_user_manage_service,
    get_version_service,
    get_progress_service,
    get_message_sender_service,
    get_tmdb_blacklist_helper,
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
)
from app.db.repositories import ConfigRepository
from app.utils import ExceptionUtils
from app.services.system_service import restart_server

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic Request Models
# ---------------------------------------------------------------------------

class EmptyRequest(BaseModel):
    """兼容前端 payload 中无 data 字段或 data 为空的情况"""
    data: Optional[dict] = None


class TmdbBlacklistRequest(BaseModel):
    tmdb_id: Optional[str] = None
    media_type: Optional[str] = None


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

@router.post("/add_tmdb_blacklist")
def add_tmdb_blacklist(
    req: TmdbBlacklistRequest,
    user: str = Depends(get_current_user),
    tmdb_helper = Depends(get_tmdb_blacklist_helper),
):
    if not tmdb_helper.is_blacklisted(req.tmdb_id, req.media_type):
        tmdb_helper.add_to_blacklist(
            tmdb_id=req.tmdb_id, media_type=req.media_type)
    return success()


@router.post("/check_message_client")
def check_message_client(
    req: MessageClientRequest,
    user: str = Depends(get_current_user),
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


@router.post("/clear_tmdb_blacklist")
def clear_tmdb_blacklist(
    req: EmptyRequest = EmptyRequest(),
    user: str = Depends(get_current_user),
    tmdb_helper = Depends(get_tmdb_blacklist_helper),
):
    if tmdb_helper.get_blacklist():
        tmdb_helper.clear_blacklist()
    return success()


@router.post("/delete_message_client")
def delete_message_client(
    req: MessageClientRequest,
    user: str = Depends(get_current_user),
    svc: MessageClientService = Depends(get_message_service),
):
    if svc.delete_client(cid=req.cid):
        return success()
    else:
        return fail()


@router.post("/delete_tmdb_blacklist")
def delete_tmdb_blacklist(
    req: TmdbBlacklistRequest,
    user: str = Depends(get_current_user),
    tmdb_helper = Depends(get_tmdb_blacklist_helper),
):
    if tmdb_helper.is_blacklisted(req.tmdb_id, req.media_type):
        tmdb_helper.remove_from_blacklist(
            tmdb_id=req.tmdb_id, media_type=req.media_type)
    return success()


@router.post("/get_message_client")
def get_message_client(
    req: MessageClientRequest,
    user: str = Depends(get_current_user),
    svc: MessageClientService = Depends(get_message_service),
):
    return success(detail=svc.get_client(cid=req.cid))


@router.post("/logout")
def logout(
    req: EmptyRequest = EmptyRequest(),
    user: str = Depends(get_current_user),
):
    # FastAPI: 登出由客户端清除 token，服务端无需额外操作
    return success()


@router.post("/net_test")
def net_test(
    req: NetTestRequest,
    user: str = Depends(get_current_user),
    svc = Depends(get_net_test_service),
):
    result = svc.test(target=req.target or "")
    return {"res": result.success, "time": "%s 毫秒" % result.time_ms}


@router.post("/reset_db_version")
def reset_db_version(
    req: EmptyRequest = EmptyRequest(),
    user: str = Depends(get_current_user),
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
    user: str = Depends(get_current_user),
):
    restart_server()
    return success()


@router.post("/restory_backup")
def restory_backup(
    req: BackupRequest,
    user: str = Depends(get_current_user),
    svc = Depends(get_backup_restore_service),
):
    filename = req.file_name
    result = svc.restore_from_backup(filename)
    if result.success:
        return success(msg=result.message)
    return fail(msg=result.message)


@router.post("/save_indexer_config")
def save_indexer_config(
    req: IndexerConfigRequest,
    user: str = Depends(get_current_user),
    svc = Depends(get_indexer_config_service),
):
    result = svc.save_config(req.data)
    if result.success and result.code == 0:
        return success()
    return fail(code=result.code, msg=result.msg)


@router.post("/save_mediaserver_config")
def save_mediaserver_config(
    req: MediaServerConfigRequest,
    user: str = Depends(get_current_user),
    svc = Depends(get_media_server_config_service),
):
    result = svc.save_config(req.data)
    if result.success and result.code == 0:
        return success()
    return fail(code=result.code, msg=result.msg)


@router.post("/sch")
def sch(
    req: SchedulerRequest,
    user: str = Depends(get_current_user),
    svc = Depends(get_scheduler_service),
):
    ok, msg = svc.start_service(item=req.item)
    if ok:
        return success(msg=msg, item=req.item)
    return success(msg=msg, item=req.item)


@router.post("/search")
def search(
    req: SearchRequest,
    user: str = Depends(get_current_user),
    svc = Depends(get_web_search_service),
):
    """
    WEB资源搜索
    前端 ajax_post 发送格式: {"search_word": "...", ...}
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


@router.post("/set_system_config")
def set_system_config(
    req: SystemConfigRequest,
    user: str = Depends(get_current_user),
    svc = Depends(get_system_config_service),
):
    if svc.set_config(req.key, req.value):
        return success()
    return fail()


@router.post("/test_message_client")
def test_message_client(
    req: TestMessageClientRequest,
    user: str = Depends(get_current_user),
    svc: MessageClientService = Depends(get_message_service),
):
    import json
    config = json.loads(req.config) if req.config else {}
    if svc.test_connection(ctype=req.type, config=config):
        return success()
    else:
        return fail()



@router.post("/update_config")
def update_config(
    req: UpdateConfigRequest,
    user: str = Depends(get_current_user),
    svc = Depends(get_config_update_service),
):
    result = svc.update_config(req.data)
    if result.success:
        return success()
    return fail()


@router.post("/update_message_client")
def update_message_client(
    req: MessageClientRequest,
    user: str = Depends(get_current_user),
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


@router.post("/user_manager")
def user_manager(
    req: UserManagerRequest,
    user: str = Depends(get_current_user),
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
        return success(success=False)
    return fail(code=-1, success=False, message=result.message or '操作失败')


@router.post("/version")
def version(
    req: EmptyRequest = EmptyRequest(),
    user: str = Depends(get_current_user),
    svc = Depends(get_version_service),
):
    info = svc.get_latest_version()
    if info.has_update:
        return success(version=info.version, url=info.url)
    return fail(code=-1, version="", url="")


@router.post("/refresh_process")
def refresh_process(
    req: ProgressRequest,
    user: str = Depends(get_current_user),
    svc = Depends(get_progress_service),
):
    result = svc.get_progress(ptype=req.type)
    if result.exists:
        return success(value=result.value, text=result.text)
    else:
        return fail(value=0, text=result.text)


@router.post("/send_custom_message")
def send_custom_message(
    req: SendCustomMessageRequest,
    user: str = Depends(get_current_user),
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


@router.post("/send_plugin_message")
def send_plugin_message(
    req: SendPluginMessageRequest,
    user: str = Depends(get_current_user),
    svc: MessageSenderService = Depends(get_message_sender_service)
):
    svc.send_plugin_message(
        title=req.title,
        text=req.text or "",
        image=req.image or "",
    )
    return success()


@router.post("/restart")
def restart_server_endpoint(
    req: EmptyRequest = EmptyRequest(),
    user: str = Depends(get_current_user),
):
    restart_server()
    return success()


@router.post("/processes")
def processes(
    req: EmptyRequest = EmptyRequest(),
    user: str = Depends(get_current_user),
):
    from app.utils.system_utils import SystemUtils
    return success(data=SystemUtils.get_all_processes())

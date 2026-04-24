"""
Utils Routes - 辅助路由（SSE流、WebSocket、文件上传等）
"""
import json
import os
import urllib.parse
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, Depends, Query, Form, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse, Response
from starlette.status import HTTP_302_FOUND

from api.deps import (
    get_current_user, get_rss_subscription_service, get_progress_helper,
    _extract_user_from_jwt, _extract_user_from_api_key
)
from app.schemas.auth import UserContext
from app.utils.temp_manager import temp_manager
from app.services.log_streaming_service import LogStreamingService

from .utils import templates

router = APIRouter()

# 初始化日志流服务
log_streaming_service = LogStreamingService(sleep_interval=1.0)


def _get_ws_user(websocket: WebSocket):
    """WebSocket 统一认证：优先 JWT/APIKey query param，兼容 Session"""
    query_params = dict(websocket.query_params)
    auth_header = query_params.get("token") or query_params.get("apikey")

    # 1) JWT
    if auth_header:
        user_ctx = _extract_user_from_jwt(auth_header)
        if user_ctx:
            return user_ctx

    # 2) API Key
    if auth_header:
        username = _extract_user_from_api_key(auth_header, query_params.get("apikey"))
        if username:
            return UserContext(user_id=0, username=username, level=0, permissions=[], is_superadmin=False)

    # 3) Session（WebSocket scope 中的 session）
    session = websocket.scope.get("session", {})
    user_id = session.get("user_id") or session.get("_user_id")
    if user_id:
        from app.services.rbac_service import rbac_service
        try:
            user = rbac_service.get_user_by_id(user_id)
            if user and getattr(user, 'STATUS', 0) == 1:
                permissions = rbac_service.get_user_permissions(user_id)
                permissions = list(permissions) if permissions else []
                return UserContext(
                    user_id=user_id,
                    username=getattr(user, 'USERNAME', ''),
                    level=getattr(user, 'LEVEL', 0) or 0,
                    permissions=permissions,
                    is_superadmin=getattr(user, 'IS_SUPERADMIN', 0) == 1
                )
        except Exception:
            pass

    return None


# ---------------------------------------------------------------------------
# 消息中心 WebSocket
# ---------------------------------------------------------------------------

@router.websocket("/message")
async def message_websocket(websocket: WebSocket):
    """消息中心 WebSocket：接收客户端 lst_time 请求并返回系统消息
    
    认证方式（优先级）：
    1. query string ?token=xxx  (JWT)
    2. query string ?apikey=xxx (API Key)
    3. Session Cookie（浏览器默认）
    """
    if not _get_ws_user(websocket):
        await websocket.close(code=1008, reason="Unauthorized")
        return

    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg_data = json.loads(data)
            except json.JSONDecodeError:
                continue

            lst_time = msg_data.get("lst_time", "")
            from app.services.system_service import get_system_message
            result = get_system_message(lst_time)
            await websocket.send_text(json.dumps(result))
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 文件上传
# ---------------------------------------------------------------------------

@router.post("/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    current_user: str = Depends(get_current_user),
):
    """上传文件到服务器"""
    try:
        file_path = Path(temp_manager.get_temp_path()) / file.filename
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)
        return {"code": 0, "filepath": str(file_path)}
    except Exception as e:
        return {"code": 1, "msg": str(e), "filepath": ""}


# ---------------------------------------------------------------------------
# 目录列表
# ---------------------------------------------------------------------------

@router.post("/dirlist")
def dirlist(
    request: Request,
    dir: str = Form(""),
    filter: Optional[str] = Form(None),
    current_user: str = Depends(get_current_user),
):
    """目录事件响应 - 文件树控件"""
    r = ['<ul class="jqueryFileTree" style="display: none;">']
    try:
        in_dir = urllib.parse.unquote(dir)
        ft = filter
        if not in_dir or in_dir == "/":
            from app.utils import SystemUtils
            from app.utils.types import OsType
            if SystemUtils.get_system() == OsType.WINDOWS:
                from app.utils import SystemUtils
                partitions = SystemUtils.get_windows_drives()
                if partitions:
                    dirs = partitions
                else:
                    dirs = [os.path.join("C:/", f) for f in os.listdir("C:/")]
            else:
                dirs = [os.path.join("/", f) for f in os.listdir("/")]
        else:
            d = os.path.normpath(urllib.parse.unquote(in_dir))
            if not os.path.isdir(d):
                d = os.path.dirname(d)
            dirs = [os.path.join(d, f) for f in os.listdir(d)]
        for ff in dirs:
            f = os.path.basename(ff)
            if not f:
                f = ff
            if os.path.isdir(ff):
                r.append('<li class="directory collapsed"><a rel="%s/">%s</a></li>' % (
                    ff.replace("\\", "/"), f.replace("\\", "/")))
            else:
                if ft != "HIDE_FILES_FILTER":
                    e = os.path.splitext(f)[1][1:]
                    r.append('<li class="file ext_%s"><a rel="%s">%s</a></li>' % (
                        e, ff.replace("\\", "/"), f.replace("\\", "/")))
        r.append('</ul>')
    except Exception as e:
        import traceback
        r.append('加载路径失败: %s' % str(e))
    r.append('</ul>')
    return Response(content=''.join(r), media_type="text/html")


# ---------------------------------------------------------------------------
# 日志流 (SSE)
# ---------------------------------------------------------------------------

@router.get("/stream-logging")
def stream_logging(
    request: Request,
    source: Optional[str] = Query(""),
    current_user: str = Depends(get_current_user),
):
    """实时日志 EventSource 响应"""
    return StreamingResponse(
        log_streaming_service.stream(source or ""),
        media_type="text/event-stream"
    )


# ---------------------------------------------------------------------------
# 进度流 (SSE)
# ---------------------------------------------------------------------------

@router.get("/stream-progress")
def stream_progress(
    request: Request,
    type: str = Query(""),
    current_user: str = Depends(get_current_user),
    progress_helper = Depends(get_progress_helper),
):
    """实时进度 EventSource 响应"""
    import json
    import time
    
    def __progress(_type):
        while True:
            time.sleep(0.2)
            detail = progress_helper.get_process(_type)
            if detail:
                detail = {"code": 0, "value": detail.get("value"), "text": detail.get("text")}
            else:
                detail = {"code": -1, "value": 0, "text": "正在处理..."}
            yield 'data: %s\n\n' % json.dumps(detail)
    
    return StreamingResponse(
        __progress(type),
        media_type="text/event-stream"
    )


# ---------------------------------------------------------------------------
# 备份下载
# ---------------------------------------------------------------------------

@router.post("/backup")
def backup(
    request: Request,
    current_user: str = Depends(get_current_user),
):
    """备份配置文件"""
    from app.services.system_service import backup as do_backup
    zip_file = do_backup()
    if not zip_file:
        return Response("创建备份失败", status_code=400)
    return FileResponse(zip_file, filename=os.path.basename(zip_file))


# ---------------------------------------------------------------------------
# robots.txt
# ---------------------------------------------------------------------------

@router.get("/robots.txt")
def robots_txt():
    """禁止搜索引擎"""
    return FileResponse("web/robots.txt")


# ---------------------------------------------------------------------------
# 健康检查
# ---------------------------------------------------------------------------

@router.get("/healthcheck")
def healthcheck():
    """健康检查"""
    return {"code": 0, "success": True, "data": {}}


# ---------------------------------------------------------------------------
# 唤起App中转页面
# ---------------------------------------------------------------------------

@router.get("/open", response_class=HTMLResponse)
def open_app_page(request: Request):
    """唤起App中转页面"""
    return templates.TemplateResponse(request, "openapp.html", {})


# ---------------------------------------------------------------------------
# iCal 日历订阅
# ---------------------------------------------------------------------------

@router.get("/ical")
def ical(
    request: Request,
    remind: Optional[str] = Query(None),
    rss_svc = Depends(get_rss_subscription_service),
):
    """iCal 日历订阅"""
    from datetime import datetime, timedelta
    from icalendar import Calendar, Event, Alarm
    
    cal = Calendar()
    rss_items = rss_svc.get_ical_events()
    for item in rss_items:
        event = Event()
        event.add('summary', f'{item.get("type")}：{item.get("title")}')
        if not item.get("start"):
            continue
        event.add('dtstart',
                  datetime.strptime(item.get("start"), '%Y-%m-%d')
                  + timedelta(hours=8))
        event.add('dtend',
                  datetime.strptime(item.get("start"), '%Y-%m-%d')
                  + timedelta(hours=9))
        
        # 添加事件提醒
        if remind:
            alarm = Alarm()
            alarm.add('trigger', timedelta(minutes=30))
            alarm.add('action', 'DISPLAY')
            event.add_component(alarm)
        
        cal.add_component(event)
    
    response = Response(cal.to_ical(), media_type='text/calendar')
    response.headers['Content-Disposition'] = 'attachment; filename=nastool.ics'
    return response

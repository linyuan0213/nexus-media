"""
FastAPI 主应用
与 Flask 应用并行存在，按领域逐步迁移 Router。
"""
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.utils.security import get_secret_key
from api.routers import system, site, download, rss, sync, brush, filter, scheduler, userrss, words, media, rbac, auth, image, plugin_framework, apikey, message_webhook
from app.message import Message
from app.plugin_framework.sandbox import PluginSandbox
import version

# 读取安全密钥（与 Flask 共用 secret_key）
_secret_key = get_secret_key()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动后台服务"""
    import log
    from app.db import init_db
    from app.services.system_service import SystemLifecycleService
    log.info("【FastAPI】初始化数据库...")
    init_db()
    log.info("【FastAPI】启动后台服务...")
    SystemLifecycleService().start_service()
    log.info("【FastAPI】后台服务启动完成")
    # 加载插件（在消息菜单刷新之前，确保插件命令能显示）
    PluginSandbox().load_all()
    log.info("【FastAPI】插件加载完成")
    # 预初始化消息客户端（避免 webhook 首次调用时客户端尚未就绪）
    Message().active_clients
    log.info("【FastAPI】消息客户端初始化完成")
    # 系统启动完成后统一刷新菜单（确保包含插件命令）
    Message().refresh_menus()
    log.info("【FastAPI】消息菜单刷新完成")
    yield
    log.info("【FastAPI】关闭后台服务...")
    SystemLifecycleService().stop_service()
    log.info("【FastAPI】后台服务已关闭")


app = FastAPI(
    title="NAS-Tools API",
    description="NAS-Tools 现代化 FastAPI 路由（P3 绞杀式迁移）",
    version=version.APP_VERSION,
    lifespan=lifespan,
)

# SessionMiddleware：兼容现有 Flask Session（Redis）
app.add_middleware(
    SessionMiddleware,
    secret_key=_secret_key,
    session_cookie="session",
    max_age=2592000,  # 30 天，与 Flask 保持一致
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session 清理中间件：每个请求结束后清理 scoped_session
@app.middleware("http")
async def db_session_cleanup(request: Request, call_next):
    """请求结束后清理数据库 session，防止 scoped_session 泄漏"""
    try:
        response = await call_next(request)
        return response
    finally:
        from app.db import remove_session
        remove_session()

# 注册 Router（按领域逐步增加）
app.include_router(system.router, prefix="/api/system", tags=["system"])
app.include_router(site.router, prefix="/api/site", tags=["site"])
app.include_router(download.router, prefix="/api/download", tags=["download"])
app.include_router(rss.router, prefix="/api/rss", tags=["rss"])
app.include_router(sync.router, prefix="/api/sync", tags=["sync"])
app.include_router(brush.router, prefix="/api/brush", tags=["brush"])
app.include_router(filter.router, prefix="/api/filter", tags=["filter"])
app.include_router(scheduler.router, prefix="/api/scheduler", tags=["scheduler"])
app.include_router(plugin_framework.router, prefix="/api/plugin-framework", tags=["plugin-framework"])
app.include_router(userrss.router, prefix="/api/userrss", tags=["userrss"])
app.include_router(words.router, prefix="/api/words", tags=["words"])
app.include_router(media.router, prefix="/api/media", tags=["media"])
app.include_router(rbac.router, prefix="/api/rbac", tags=["rbac"])
app.include_router(auth.router, tags=["authentication"])
app.include_router(image.router, prefix="/img", tags=["image"])
app.include_router(apikey.router, prefix="/api/apikey", tags=["apikey"])
# 消息客户端 webhook（不需要 /api 前缀）
app.include_router(message_webhook.router, tags=["message-webhook"])

# 挂载静态文件（与 Flask 共用 web/static）
_static_dir = os.path.join(os.path.dirname(__file__), "..", "web", "static")
app.mount("/static", StaticFiles(directory=_static_dir), name="static")


@app.get("/health")
def health_check():
    """健康检查"""
    return {"status": "ok", "version": version.APP_VERSION}


from starlette.responses import JSONResponse


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """
    全局 HTTP 异常处理器
    当页面路由返回 401 时，自动重定向到登录页（兼容浏览器行为）
    """
    if exc.status_code == 401:
        accept = request.headers.get("accept", "")
        # 仅当浏览器页面请求（text/html）时自动跳转登录页
        # API 请求（application/json 或 */*）保持 401 JSON 响应
        if "text/html" in accept:
            return RedirectResponse(url="/", status_code=302)
    # 其他情况返回默认 JSON 响应
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=dict(exc.headers) if exc.headers else None,
    )

"""
FastAPI 主应用
与 Flask 应用并行存在，按领域逐步迁移 Router。
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from scalar_fastapi import get_scalar_api_reference
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

import log
import version
from api.routers import (
    apikey,
    auth,
    brush,
    download,
    filter,
    image,
    media,
    message_webhook,
    plugin_framework,
    rbac,
    rss_automation,
    scheduler,
    site,
    storage_backend,
    subscription,
    sync,
    system,
    words,
)
from app.core.root_path import get_project_root
from app.core.settings import settings
from app.db import init_db
from app.db.engine import get_engine
from app.db.session import remove_session
from app.di import container
from app.downloader.client import init_clients as init_downloaders
from app.indexer.client import init_clients as init_indexers
from app.infrastructure.rate_limiter import RateLimitMiddleware
from app.infrastructure.redis import RedisStore
from app.infrastructure.security import get_secret_key
from app.mediaserver.client import init_clients as init_mediaservers
from app.message.client.manager import init_clients as init_message_clients
from app.schemas.common import HealthCheckResponse, HealthServiceStatus
from app.services.site_config_updater import SiteConfigUpdater, update_site_config_at_startup
from app.sites.engine import SiteEngine

# 读取安全密钥（与 Flask 共用 secret_key）
_secret_key = get_secret_key()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动后台服务"""
    log.info("[FastAPI]初始化数据库表结构...")
    init_db()
    log.info("[FastAPI]初始化站点配置...")
    try:
        updater = SiteConfigUpdater()
        updater.ensure_local_sites(SiteEngine._BUILTIN_DEFINITIONS_DIR)
        update_site_config_at_startup()
    except Exception as e:
        log.warn(f"[FastAPI]站点配置初始化失败: {e!s}")
    log.info("[FastAPI]启动后台服务...")
    container.system_lifecycle_service().start_service()
    log.info("[FastAPI]后台服务启动完成")
    # 注册内置索引器
    init_indexers()
    log.info("[FastAPI]索引器注册完成")
    # 注册内置下载器
    init_downloaders()
    log.info("[FastAPI]下载器注册完成")
    # 注册内置媒体服务器
    init_mediaservers()
    log.info("[FastAPI]媒体服务器注册完成")
    # 注册内置消息客户端
    init_message_clients()
    log.info("[FastAPI]消息客户端注册完成")
    # 加载插件（在消息菜单刷新之前，确保插件命令能显示）
    container.plugin_sandbox().load_all()
    log.info("[FastAPI]插件加载完成")
    # 预初始化消息客户端（避免 webhook 首次调用时客户端尚未就绪）
    _ = container.message().active_clients
    log.info("[FastAPI]消息客户端初始化完成")
    # 系统启动完成后统一刷新菜单（确保包含插件命令）
    container.message().refresh_menus()
    log.info("[FastAPI]消息菜单刷新完成")
    yield
    log.info("[FastAPI]关闭后台服务...")
    container.system_lifecycle_service().stop_service()
    log.info("[FastAPI]后台服务已关闭")


app = FastAPI(
    title="Nexus Media API",
    description="Nexus Media 现代化 FastAPI 路由（P3 绞杀式迁移）",
    version=version.APP_VERSION,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)


_debug = bool((settings.get("app") or {}).get("debug"))

if _debug:

    @app.get("/docs", include_in_schema=False)
    async def scalar_html():
        return get_scalar_api_reference(
            openapi_url=app.openapi_url,
            title=app.title,
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


# 速率限制中间件：Redis 可用时分布式限流，否则降级为内存限流
app.add_middleware(RateLimitMiddleware, rate="60/m")


# Session 清理中间件：每个请求结束后清理 scoped_session
@app.middleware("http")
async def db_session_cleanup(request: Request, call_next):
    """请求结束后清理数据库 session，防止 scoped_session 泄漏"""
    try:
        response = await call_next(request)
        return response
    finally:
        remove_session()


# 注册 Router（按领域逐步增加）
app.include_router(system.router, prefix="/api/system", tags=["system"])
app.include_router(site.router, prefix="/api/site", tags=["site"])
app.include_router(download.router, prefix="/api/download", tags=["download"])
app.include_router(subscription.router, prefix="/api/subscription", tags=["subscription"])
app.include_router(sync.router, prefix="/api/sync", tags=["sync"])
app.include_router(storage_backend.router, prefix="/api/storage", tags=["storage"])
app.include_router(brush.router, prefix="/api/brush", tags=["brush"])
app.include_router(filter.router, prefix="/api/filter", tags=["filter"])
app.include_router(scheduler.router, prefix="/api/scheduler", tags=["scheduler"])
app.include_router(plugin_framework.router, prefix="/api/plugin-framework", tags=["plugin-framework"])
app.include_router(rss_automation.router, prefix="/api/rss-automation", tags=["rss-automation"])
app.include_router(words.router, prefix="/api/words", tags=["words"])
app.include_router(media.router, prefix="/api/media", tags=["media"])
app.include_router(rbac.router, prefix="/api/rbac", tags=["rbac"])
app.include_router(auth.router, tags=["authentication"])
app.include_router(image.router, prefix="/img", tags=["image"])
app.include_router(apikey.router, prefix="/api/apikey", tags=["apikey"])
# 消息客户端 webhook（不需要 /api 前缀）
app.include_router(message_webhook.router, tags=["message-webhook"])

# 挂载静态文件
_static_dir = str(get_project_root() / "static")
app.mount("/static", StaticFiles(directory=_static_dir), name="static")


@app.get("/health", response_model=HealthCheckResponse, summary="健康检查")
def health_check():
    """健康检查：验证数据库、Redis 及关键外部服务的可用性"""
    result = HealthCheckResponse(status="ok", version=version.APP_VERSION)

    # 数据库检查
    try:
        engine = get_engine()
        if engine is None:
            raise RuntimeError("数据库引擎未初始化")
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        result.database = HealthServiceStatus(status="ok", detail="数据库连接正常")
    except Exception as e:
        result.status = "degraded"
        result.database = HealthServiceStatus(status="error", detail=f"数据库连接失败: {e!s}")

    # Redis 检查
    try:
        redis_ok = RedisStore().ping()
        if redis_ok:
            result.redis = HealthServiceStatus(status="ok", detail="Redis 连接正常")
        else:
            result.status = "degraded"
            result.redis = HealthServiceStatus(status="error", detail="Redis 不可用")
    except Exception as e:
        result.status = "degraded"
        result.redis = HealthServiceStatus(status="error", detail=f"Redis 检查失败: {e!s}")

    # 关键外部服务：消息客户端
    try:
        msg_clients = container.message().active_clients
        result.services["message"] = HealthServiceStatus(status="ok", detail=f"已配置 {len(msg_clients)} 个消息客户端")
    except Exception as e:
        result.services["message"] = HealthServiceStatus(status="error", detail=f"消息客户端检查失败: {e!s}")

    return result


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

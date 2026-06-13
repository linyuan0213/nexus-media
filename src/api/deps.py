"""
FastAPI 依赖注入
提供当前用户、认证、配置等通用依赖。
支持 JWT + Session 双轨认证（绞杀期）。
"""

import uuid
from typing import Any, cast

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.di.registry import registry
from app.di.types import RegistryKey
from app.infrastructure.cache_system import TokenCache
from app.infrastructure.security import generate_access_token, identify
from app.schemas.auth import UserContext
from app.services.auth_service import AuthService
from app.services.config_reloader import ConfigReloader
from app.services.config_service import ConfigService
from app.services.subscribe.management.calendar_service import SubscribeCalendarService
from app.services.subscribe.management.history_service import SubscribeHistoryService
from app.services.subscribe.management.service import SubscribeService
from app.services.system.config import ConfigUpdateService

# OAuth2 / Bearer 方案
bearer_scheme = HTTPBearer(auto_error=False)
bearer_scheme_dependency = Depends(bearer_scheme)


def _get_service(name: str | RegistryKey) -> Any:
    """通用服务工厂 — 从 Registry 获取指定名称的实例。"""
    key = RegistryKey(name) if isinstance(name, str) else name
    return registry.get(key)


def _extract_user_from_token(auth_header: str | None) -> str | None:
    """
    Token 认证（APIv1 ClientResource / Bearer）
    """
    if not auth_header:
        return None
    latest_token = TokenCache.get(auth_header)
    if not latest_token:
        return None
    flag, username = identify(latest_token)
    if not username:
        return None
    if not flag:
        # Token 过期但合法，自动续期
        TokenCache.set(auth_header, generate_access_token(username))
    return username


def _extract_user_from_api_key(
    auth_header: str | None, query_key: str | None, apikey_service=None, rbac_service=None
) -> UserContext | None:
    """
    API Key 认证（支持 Header 和 Query 参数）
    使用 APIKeyService 验证 Key 并返回 UserContext
    """

    raw_key = None
    if auth_header:
        raw_key = str(auth_header).split()[-1]
    elif query_key:
        raw_key = query_key

    if not raw_key:
        return None

    _apikey_service = apikey_service or registry.get(RegistryKey.APIKEY_SERVICE)
    api_key = _apikey_service.validate_key(raw_key)
    if not api_key:
        return None

    # 记录使用日志（异步记录，不阻塞认证流程）
    try:
        _apikey_service.record_usage(
            api_key_id=api_key.id,
            request_id=str(uuid.uuid4()),
            request_name="API 认证",
            status=1,
        )
    except Exception:
        pass

    # 查询创建用户的权限，API Key 继承创建者权限
    permissions = []
    is_superadmin = False
    level = 0
    username: str = "api_key"
    nickname = cast(str, api_key.name)
    created_by = api_key.created_by or 0

    if created_by:
        _rbac_service = rbac_service or registry.get(RegistryKey.RBAC_SERVICE)
        try:
            user = _rbac_service.get_user_by_id(created_by)
            if user is not None:
                username = cast(str, getattr(user, "USERNAME", username) or username)
                nickname = cast(str, api_key.name)
                level = getattr(user, "LEVEL", 0) or 0
                is_superadmin = getattr(user, "IS_SUPERADMIN", 0) == 1
                try:
                    perms = _rbac_service.get_user_permissions(created_by)
                    permissions = list(perms) if perms else []
                except Exception:
                    pass
        except Exception:
            pass

    return UserContext(
        user_id=created_by,
        username=username,
        nickname=nickname,
        level=level,
        permissions=permissions,
        is_superadmin=is_superadmin,
    )


def get_auth_service() -> AuthService:
    try:
        rbac = registry.get(RegistryKey.RBAC_SERVICE)
    except KeyError:
        from unittest.mock import MagicMock

        rbac = MagicMock()
    return AuthService(rbac_service=rbac)


def _extract_user_from_jwt(auth_header: str | None) -> UserContext | None:
    """
    JWT 认证：从 Authorization header 提取并验证 JWT Token
    """
    if not auth_header:
        return None
    # 支持 "Bearer xxx" 或直接 "xxx"
    token = auth_header.split()[-1] if " " in auth_header else auth_header
    return AuthService.verify_token(token)


def _extract_user_ctx_from_session(request: Request, rbac_service=None) -> UserContext | None:
    """
    从 Session 中提取用户上下文（绞杀期兼容）
    """
    session = getattr(request, "session", None)
    if not session:
        return None
    # 兼容新旧 session 键名
    user_id = session.get("user_id") or session.get("_user_id")
    if not user_id:
        return None
    try:
        _rbac_service = rbac_service or registry.get(RegistryKey.RBAC_SERVICE)
        user = _rbac_service.get_user_by_id(user_id)
        if user is None or getattr(user, "STATUS", 0) != 1:
            return None

        # 获取权限
        try:
            permissions = _rbac_service.get_user_permissions(user_id)
            permissions = list(permissions) if permissions else []
        except Exception:
            permissions = []

        level = getattr(user, "LEVEL", 0) or 0
        is_superadmin = getattr(user, "IS_SUPERADMIN", 0) == 1

        return UserContext(
            user_id=user_id,
            username=getattr(user, "USERNAME", ""),
            nickname=getattr(user, "NICKNAME", None) or None,
            level=level,
            permissions=permissions,
            is_superadmin=is_superadmin,
        )
    except Exception:
        return None


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = bearer_scheme_dependency,
) -> UserContext:
    """
    统一认证依赖：优先 JWT，兼容 Session、旧 Token(Bearer)、API Key。
    返回 UserContext；认证失败时抛出 401。
    """
    auth_header: str | None = credentials.credentials if credentials else None

    # 1) JWT 认证（新标准）
    user_ctx = _extract_user_from_jwt(auth_header)
    if user_ctx:
        return user_ctx

    # 2) Session 认证（Web 前端，绞杀期兼容）
    user_ctx = _extract_user_ctx_from_session(request)
    if user_ctx:
        return user_ctx

    # 3) 旧 Token 认证（APIv1 兼容）
    username = _extract_user_from_token(auth_header)
    if username:
        return UserContext(user_id=0, username=username, level=0, permissions=[], is_superadmin=False)

    # 4) API Key 认证
    query_key = request.query_params.get("apikey")
    user_ctx = _extract_user_from_api_key(auth_header, query_key)
    if user_ctx:
        return user_ctx

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="安全认证未通过，请检查登录状态、Token 或 ApiKey",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user_optional(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = bearer_scheme_dependency,
) -> UserContext | None:
    """
    可选认证：未登录返回 None，不抛异常。
    """
    try:
        return get_current_user(request, credentials)
    except HTTPException:
        return None


current_user_dependency = Depends(get_current_user)


def require_permission(permission: str):
    """
    权限检查装饰器工厂
    用法: user = Depends(require_permission("download:read"))
    """

    def checker(user: UserContext = current_user_dependency) -> UserContext:
        if permission not in user.permissions and not user.is_superadmin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"权限不足: {permission}")
        return user

    return checker


def require_any_permission(*permissions: str):
    """
    权限检查装饰器工厂（满足任一权限即可）
    用法: user = Depends(require_any_permission("download:view", "download:manage"))
    """

    def checker(user: UserContext = current_user_dependency) -> UserContext:
        if user.is_superadmin:
            return user
        if any(p in user.permissions for p in permissions):
            return user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=f"权限不足，需要以下任一权限: {', '.join(permissions)}"
        )

    return checker


def require_all_permissions(*permissions: str):
    """
    权限检查装饰器工厂（需满足所有权限）
    用法: user = Depends(require_all_permissions("user:view", "user:update"))
    """

    def checker(user: UserContext = current_user_dependency) -> UserContext:
        if user.is_superadmin:
            return user
        missing = [p for p in permissions if p not in user.permissions]
        if missing:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"权限不足，缺少: {', '.join(missing)}")
        return user

    return checker


def get_config_service() -> ConfigService:
    """获取配置服务实例"""
    return _get_service("config_service")


def get_message_service():
    """获取消息客户端服务实例"""
    return _get_service("message_client_service")


def get_message():
    """获取消息门面实例"""
    return _get_service(RegistryKey.MESSAGE)


# --- 领域 Service 工厂 ---


def get_download_service():
    """获取下载服务实例"""
    return _get_service("download_service")


def get_site_service():
    """获取站点服务实例"""
    return _get_service("site_service")


def get_indexer_service():
    """获取索引器服务实例"""
    return _get_service(RegistryKey.INDEXER_SERVICE)


def get_media_info_service():
    """获取媒体信息服务实例"""
    return _get_service("media_info_service")


def get_media_library_service():
    """获取媒体库服务实例"""
    return _get_service("media_library_service")


def get_media_file_service():
    """获取媒体文件服务实例"""
    return _get_service("media_file_service")


def get_file_index_service():
    """获取文件索引服务实例"""
    return _get_service("file_index_service")


def get_transfer_history_service():
    """获取转移历史服务实例"""
    return _get_service("transfer_history_service")


def get_search_result_service():
    """获取搜索结果服务实例"""
    return _get_service("search_result_service")


def get_sync_service():
    """获取同步服务实例"""
    return _get_service(RegistryKey.SYNC_SERVICE)


def get_subscribe_service() -> SubscribeService:
    """获取订阅服务实例"""
    return _get_service(RegistryKey.SUBSCRIBE_SERVICE)


def get_subscribe_history_service() -> SubscribeHistoryService:
    """获取订阅历史服务实例"""
    return _get_service("subscribe_history_service")


def get_subscribe_calendar_service() -> SubscribeCalendarService:
    """获取订阅日历服务实例"""
    return _get_service("subscribe_calendar_service")


def get_brush_service():
    """获取刷流服务实例"""
    return _get_service("brush_service")


def get_plugin_framework_service():
    """获取插件框架 v2 服务实例"""
    return _get_service("plugin_framework_service")


def get_words_service():
    """获取自定义识别词服务实例"""
    return _get_service("words_service")


def get_user_rss_service():
    """获取用户 RSS 服务实例"""
    return _get_service("user_rss_service")


def get_scheduler_service():
    """获取调度器服务实例"""
    return _get_service("scheduler_service")


def get_system_scheduler_service():
    """获取系统调度器服务实例（用于启动后台服务）"""
    return _get_service(RegistryKey.SCHEDULER_CORE)


def get_filter_service():
    """获取过滤服务实例"""
    return _get_service("filter_service")


def get_net_test_service():
    """获取网络测试服务实例"""
    return _get_service("net_test_service")


def get_apikey_service():
    """获取 API Key 服务实例"""
    return _get_service("apikey_service")


def get_system_config_service():
    """获取系统配置服务实例"""
    return _get_service("system_config_service")


def get_config_update_service():
    """获取配置更新服务实例"""
    return ConfigUpdateService()


def get_user_manage_service():
    """获取用户管理服务实例"""
    return _get_service("user_manage_service")


def get_progress_service():
    """获取进度服务实例"""
    return _get_service("progress_service")


def get_message_sender_service():
    """获取消息发送服务实例"""
    return _get_service("message_sender_service")


def get_system_info_service():
    """获取系统信息服务实例"""
    return _get_service("system_info_service")


def get_system_lifecycle_service():
    """获取系统生命周期服务实例"""
    return _get_service(RegistryKey.SYSTEM_LIFECYCLE)


def get_backup_restore_service():
    """获取备份恢复服务实例"""
    return _get_service("backup_restore_service")


def get_indexer_config_service():
    """获取索引器配置服务实例"""
    return _get_service("indexer_config_service")


def get_media_server_config_service():
    """获取媒体服务器配置服务实例"""
    return _get_service("media_server_config_service")


def get_web_search_service():
    """获取 Web 搜索服务实例"""
    return _get_service("web_search_service")


def get_downloader_service():
    """获取下载器核心服务实例"""
    return _get_service(RegistryKey.DOWNLOADER_CORE)


def get_filetransfer_service():
    """获取文件转移服务实例"""
    return _get_service("filetransfer_service")


def get_media_recommendation_service():
    """获取媒体推荐服务实例"""
    return _get_service("media_recommendation_service")


def get_searcher_service():
    """获取搜索服务实例"""
    return _get_service(RegistryKey.SEARCHER)


def get_tmdb_blacklist_service():
    """获取 TMDB 黑名单服务实例"""
    return _get_service("tmdb_blacklist_service")


def get_thread_executor():
    """获取线程助手实例"""
    return _get_service("thread_executor")


def get_media_config_service():
    """获取媒体库路径配置服务"""
    return _get_service("media_config_service")


def get_storage_backend_service():
    """获取存储后端服务实例"""
    return _get_service("storage_backend_service")


def get_rbac_service():
    """获取 RBAC 服务实例"""
    return _get_service("rbac_service")


def get_subscription_monitor():
    """获取订阅监控实例"""
    lifecycle = _get_service(RegistryKey.SYSTEM_LIFECYCLE)
    return lifecycle.subscription_monitor


def get_hook_system():
    """获取 Hook 系统实例"""
    return _get_service(RegistryKey.HOOK_SYSTEM)


def get_config_reloader():
    """获取配置重载器实例"""
    return ConfigReloader(provider_resolver=registry.get)

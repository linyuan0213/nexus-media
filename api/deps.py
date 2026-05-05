"""
FastAPI 依赖注入
提供当前用户、认证、配置等通用依赖。
支持 JWT + Session 双轨认证（绞杀期）。
"""
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.schemas.auth import UserContext
from app.services.auth_service import AuthService
from app.services.rbac_service import rbac_service
from app.services.config_service import ConfigService
from app.utils.security import identify, generate_access_token
from app.utils import TokenCache
from config import Config

# OAuth2 / Bearer 方案
bearer_scheme = HTTPBearer(auto_error=False)


def _extract_user_from_session(request: Request) -> Optional[str]:
    """
    从 Session 中提取当前登录用户。
    """
    session = getattr(request, "session", None)
    if not session:
        return None
    user_id = session.get("_user_id")
    if not user_id:
        return None
    # 通过 RBAC Service 查询用户名
    try:
        user = rbac_service.get_user_by_id(user_id)
        if user and user.STATUS == 1:
            return user.USERNAME
    except Exception:
        pass
    return None


def _extract_user_from_token(auth_header: Optional[str]) -> Optional[str]:
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
    auth_header: Optional[str], query_key: Optional[str]
) -> Optional[str]:
    """
    API Key 认证（APIv1 ApiResource / 外部调用）
    """
    api_key = Config().get_config("security").get("api_key")
    if not api_key:
        return None
    if auth_header:
        auth_val = str(auth_header).split()[-1]
        if auth_val == api_key:
            return "api"
    if query_key and query_key == api_key:
        return "api"
    return None


def _extract_user_from_jwt(
    auth_header: Optional[str]
) -> Optional[UserContext]:
    """
    JWT 认证：从 Authorization header 提取并验证 JWT Token
    """
    if not auth_header:
        return None
    # 支持 "Bearer xxx" 或直接 "xxx"
    token = auth_header.split()[-1] if " " in auth_header else auth_header
    return AuthService.verify_token(token)


def _extract_user_ctx_from_session(request: Request) -> Optional[UserContext]:
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
        user = rbac_service.get_user_by_id(user_id)
        if not user or user.STATUS != 1:
            return None

        # 获取权限
        try:
            permissions = rbac_service.get_user_permissions(user_id)
            permissions = list(permissions) if permissions else []
        except Exception:
            permissions = []

        level = getattr(user, 'LEVEL', 0) or 0
        is_superadmin = getattr(user, 'IS_SUPERADMIN', 0) == 1

        return UserContext(
            user_id=user_id,
            username=getattr(user, 'USERNAME', ''),
            nickname=getattr(user, 'NICKNAME', None) or None,
            level=level,
            permissions=permissions,
            is_superadmin=is_superadmin
        )
    except Exception:
        return None


def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> UserContext:
    """
    统一认证依赖：优先 JWT，兼容 Session、旧 Token(Bearer)、API Key。
    返回 UserContext；认证失败时抛出 401。
    """
    auth_header: Optional[str] = credentials.credentials if credentials else None

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
        return UserContext(
            user_id=0,
            username=username,
            level=0,
            permissions=[],
            is_superadmin=False
        )

    # 4) API Key 认证
    query_key = request.query_params.get("apikey")
    username = _extract_user_from_api_key(auth_header, query_key)
    if username:
        return UserContext(
            user_id=0,
            username=username,
            level=0,
            permissions=[],
            is_superadmin=False
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="安全认证未通过，请检查登录状态、Token 或 ApiKey",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[UserContext]:
    """
    可选认证：未登录返回 None，不抛异常。
    """
    try:
        return get_current_user(request, credentials)
    except HTTPException:
        return None


def require_permission(permission: str):
    """
    权限检查装饰器工厂
    用法: user = Depends(require_permission("download:read"))
    """
    def checker(user: UserContext = Depends(get_current_user)) -> UserContext:
        if permission not in user.permissions and not user.is_superadmin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足: {permission}"
            )
        return user
    return checker


def require_any_permission(*permissions: str):
    """
    权限检查装饰器工厂（满足任一权限即可）
    用法: user = Depends(require_any_permission("download:view", "download:manage"))
    """
    def checker(user: UserContext = Depends(get_current_user)) -> UserContext:
        if user.is_superadmin:
            return user
        if any(p in user.permissions for p in permissions):
            return user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"权限不足，需要以下任一权限: {', '.join(permissions)}"
        )
    return checker


def require_all_permissions(*permissions: str):
    """
    权限检查装饰器工厂（需满足所有权限）
    用法: user = Depends(require_all_permissions("user:view", "user:update"))
    """
    def checker(user: UserContext = Depends(get_current_user)) -> UserContext:
        if user.is_superadmin:
            return user
        missing = [p for p in permissions if p not in user.permissions]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足，缺少: {', '.join(missing)}"
            )
        return user
    return checker





# ---------------------------------------------------------------------------
# 依赖注入工厂（DI Container 轻量级实现）
# 路由层统一通过 Depends 注入，不再直接引用全局单例。
# ---------------------------------------------------------------------------

from typing import TypeVar, Callable, Any

_F = TypeVar("_F", bound=Callable[..., Any])


def get_config_service() -> ConfigService:
    """获取配置服务实例"""
    return ConfigService()


def get_message_service():
    """获取消息客户端服务实例（避免路由层直接实例化 MessageClientService）"""
    from app.services.system_service import MessageClientService
    return MessageClientService()


# --- 领域 Service 工厂 ---


def get_download_service():
    """获取下载服务实例"""
    from app.services.download_service import DownloadService
    return DownloadService()


def get_site_service():
    """获取站点服务实例"""
    from app.services.site_service import SiteService
    return SiteService()


def get_indexer_service():
    """获取索引器服务实例"""
    from app.services.indexer_service import IndexerService
    return IndexerService()


def get_media_info_service():
    """获取媒体信息服务实例"""
    from app.services.media_service import MediaInfoService
    return MediaInfoService()


def get_media_library_service():
    """获取媒体库服务实例"""
    from app.services.media_service import MediaLibraryService
    return MediaLibraryService()


def get_media_file_service():
    """获取媒体文件服务实例"""
    from app.services.media_service import MediaFileService
    return MediaFileService()


def get_transfer_history_service():
    """获取转移历史服务实例"""
    from app.services.media_service import TransferHistoryService
    return TransferHistoryService()


def get_search_result_service():
    """获取搜索结果服务实例"""
    from app.services.media_service import SearchResultService
    return SearchResultService()


def get_sync_service():
    """获取同步服务实例"""
    from app.services.sync_service import SyncService
    return SyncService()


def get_rss_subscription_service():
    """获取 RSS 订阅服务实例"""
    from app.services.rss_service import RssSubscriptionService
    return RssSubscriptionService()


def get_rss_task_service():
    """获取 RSS 任务服务实例"""
    from app.services.rss_service import RssTaskService
    return RssTaskService()


def get_brush_service():
    """获取刷流服务实例"""
    from app.services.brush_service import BrushService
    return BrushService()


def get_brush_task_service():
    """获取刷流任务核心服务实例"""
    from app.services.brush_core import BrushTaskService
    return BrushTaskService()


def get_plugin_framework_service():
    """获取插件框架 v2 服务实例"""
    from app.services.plugin_framework_service import PluginFrameworkService
    return PluginFrameworkService()


def get_words_service():
    """获取自定义识别词服务实例"""
    from app.services.words_service import WordsService
    return WordsService()


def get_user_rss_service():
    """获取用户 RSS 服务实例"""
    from app.services.userrss_service import UserRssService
    return UserRssService()


def get_scheduler_service():
    """获取调度器服务实例"""
    from app.services.scheduler_service import SchedulerService
    return SchedulerService()


def get_system_scheduler_service():
    """获取系统调度器服务实例（用于启动后台服务）"""
    from app.services.system_service import SchedulerService
    return SchedulerService()


def get_filter_service():
    """获取过滤服务实例"""
    from app.services.filter_service import FilterService
    return FilterService()


def get_net_test_service():
    """获取网络测试服务实例"""
    from app.services.system_service import NetTestService
    return NetTestService()


def get_version_service():
    """获取版本服务实例"""
    from app.services.system_service import VersionService
    return VersionService()


def get_system_config_service():
    """获取系统配置服务实例"""
    from app.services.system_service import SystemConfigService
    return SystemConfigService()


def get_config_update_service():
    """获取配置更新服务实例"""
    from app.services.system_service import ConfigUpdateService
    return ConfigUpdateService()


def get_user_manage_service():
    """获取用户管理服务实例"""
    from app.services.system_service import UserManageService
    return UserManageService()


def get_progress_service():
    """获取进度服务实例"""
    from app.services.system_service import ProgressService
    return ProgressService()


def get_message_sender_service():
    """获取消息发送服务实例"""
    from app.services.system_service import MessageSenderService
    return MessageSenderService()


def get_system_info_service():
    """获取系统信息服务实例"""
    from app.services.system_service import SystemInfoService
    return SystemInfoService()


def get_backup_restore_service():
    """获取备份恢复服务实例"""
    from app.services.system_service import BackupRestoreService
    return BackupRestoreService()


def get_indexer_config_service():
    """获取索引器配置服务实例"""
    from app.services.system_service import IndexerConfigService
    return IndexerConfigService()


def get_media_server_config_service():
    """获取媒体服务器配置服务实例"""
    from app.services.system_service import MediaServerConfigService
    return MediaServerConfigService()


def get_web_search_service():
    """获取 Web 搜索服务实例"""
    from app.services.system_service import WebSearchService
    return WebSearchService()


def get_downloader_service():
    """获取下载器核心服务实例"""
    from app.services.downloader_core import DownloaderCore
    return DownloaderCore()


def get_filetransfer_service():
    """获取文件转移服务实例"""
    from app.services.filetransfer_service import FileTransferService
    return FileTransferService()


def get_torrent_remover_service():
    """获取种子删除服务实例"""
    from app.services.torrentremover_core import TorrentRemoverService
    return TorrentRemoverService()


def get_media_recommendation_service():
    """获取媒体推荐服务实例"""
    from app.services.media_service import MediaRecommendationService
    return MediaRecommendationService()


def get_searcher_service():
    """获取搜索服务实例"""
    from app.services.search_service import Searcher
    return Searcher()


def get_tmdb_blacklist_service():
    """获取 TMDB 黑名单服务实例"""
    from app.services.tmdb_blacklist_service import TmdbBlacklistService
    return TmdbBlacklistService()


def get_progress_helper():
    """获取进度助手实例"""
    from app.helper.progress_helper import ProgressHelper
    return ProgressHelper()


def get_drissionpage_helper():
    """获取 DrissionPage 助手实例"""
    from app.helper.drissionpage_helper import DrissionPageHelper
    return DrissionPageHelper()


def get_thread_helper():
    """获取线程助手实例"""
    from app.helper import ThreadHelper
    return ThreadHelper()

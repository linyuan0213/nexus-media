"""
Nexus Media 统一异常体系

层次结构：
    NexusError (基类)
    ├── DomainError          领域/业务逻辑异常
    │   ├── MediaError       媒体识别、刮削相关
    │   ├── BrushError       刷流任务相关
    │   ├── SubscribeError   订阅相关
    │   └── SyncError        同步相关
    ├── RepositoryError      数据仓储异常
    │   ├── DatabaseError    数据库连接/查询失败
    │   └── CacheError       缓存操作失败
    ├── ServiceError         服务层异常
    │   ├── AuthError        认证/授权失败
    │   ├── ConfigError      配置读取/校验失败
    │   └── SchedulerError   定时任务异常
    ├── InfrastructureError  基础设施/外部服务异常
    │   ├── NetworkError     网络请求失败
    │   ├── DownloadError    下载器通信失败
    │   ├── IndexerError     索引器/站点访问失败
    │   ├── MessageError     消息推送失败
    │   └── TMDBError        TMDB API 错误 (兼容旧类)
    └── ValidationError      输入参数校验失败

使用约定：
- 捕获时优先捕获具体异常类型，避免裸 `except Exception`。
- 如需统一兜底，捕获 `NexusError` 而非 `Exception`。
- 异常消息应包含足够上下文，便于排查。
"""

from __future__ import annotations


class NexusError(Exception):
    """应用根异常"""

    def __init__(self, message: str = "", *, code: str | None = None, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.code = code or self._default_code()
        self.details = details or {}

    def _default_code(self) -> str:
        return self.__class__.__name__

    def __str__(self) -> str:
        if self.details:
            return f"[{self.code}] {self.message} | details={self.details}"
        return f"[{self.code}] {self.message}"

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


# ------------------------------------------------------------------
# Domain 层
# ------------------------------------------------------------------


class DomainError(NexusError):
    """领域逻辑异常"""


class MediaError(DomainError):
    """媒体识别、刮削、元数据异常"""


class BrushError(DomainError):
    """刷流任务规则/执行异常"""


class SubscribeError(DomainError):
    """RSS/订阅异常"""


class SyncError(DomainError):
    """媒体库同步异常"""


# ------------------------------------------------------------------
# Repository 层
# ------------------------------------------------------------------


class RepositoryError(NexusError):
    """数据仓储异常"""


class DatabaseError(RepositoryError):
    """数据库连接/查询/写入失败"""


class CacheError(RepositoryError):
    """缓存读写失败"""


class MigrationError(RepositoryError):
    """数据库迁移失败"""


# ------------------------------------------------------------------
# Service 层
# ------------------------------------------------------------------


class ServiceError(NexusError):
    """服务层异常"""


class AuthError(ServiceError):
    """认证或授权失败"""


class PermissionDenied(AuthError):
    """权限不足"""


class ConfigError(ServiceError):
    """配置读取、校验、迁移失败"""


class SchedulerError(ServiceError):
    """定时任务调度异常"""


# ------------------------------------------------------------------
# Infrastructure 层
# ------------------------------------------------------------------


class InfrastructureError(NexusError):
    """基础设施/外部服务异常"""


class NetworkError(InfrastructureError):
    """通用网络请求失败"""


class DownloadError(InfrastructureError):
    """下载器客户端通信/操作失败"""


class IndexerError(InfrastructureError):
    """索引器/站点访问失败"""


class MessageError(InfrastructureError):
    """消息推送渠道异常"""


class MediaServerError(InfrastructureError):
    """媒体服务器(Emby/Jellyfin/Plex)通信失败"""


class StorageError(InfrastructureError):
    """存储后端(S3/SMB/WebDAV等)操作失败"""


class PluginError(InfrastructureError):
    """插件加载/执行失败"""


# ------------------------------------------------------------------
# Validation 层
# ------------------------------------------------------------------


class ValidationError(NexusError):
    """输入参数校验失败"""


class MissingFieldError(ValidationError):
    """缺少必填字段"""


class InvalidValueError(ValidationError):
    """字段值非法"""


# ------------------------------------------------------------------
# 兼容旧 TMDBError（保留同名，改继承链）
# ------------------------------------------------------------------


class TMDBError(InfrastructureError):
    """TMDB API 调用失败（兼容旧类，继承链已改为 InfrastructureError）"""

# Repository Layer for Database Operations
# Provides clean separation of data access logic

from .apikey_repo_adapter import (
    APIKeyLogRepositoryAdapter,
    APIKeyRepositoryAdapter,
)
from .apikey_repository import (
    APIKeyLogRepository,
    APIKeyRepository,
)
from .base_repository import BaseRepository
from .brush_repository import BrushRepository
from .config_repository import ConfigRepository
from .download_repository import DownloadRepository
from .media_repo_adapter import MediaInfoRepositoryAdapter
from .media_repository import MediaInfoRepository, MediaRecord
from .media_sync_repo_adapter import MediaSyncRepositoryAdapter
from .media_sync_repository import MediaSyncRepository
from .plugin_framework_repo_adapter import (
    PluginConfigRepositoryAdapter,
    PluginLogRepositoryAdapter,
    PluginManifestRepositoryAdapter,
)
from .plugin_framework_repository import PluginFrameworkRepository
from .plugin_repository import PluginRepository
from .rbac_repository import (
    RBACLogRepository,
    RBACMenuRepository,
    RBACPermissionRepository,
    RBACRoleRepository,
    RBACUserRepository,
)
from .rss_repository import RssRepository
from .rss_torrent_repo_adapter import RssTorrentRepositoryAdapter
from .search_repository import SearchRepository
from .site_repository import SiteRepository
from .sync_repository import SyncRepository
from .system_dict_repo_adapter import SystemDictRepositoryAdapter
from .system_dict_repository import SystemDictRepository
from .transfer_repository import TransferRepository
from .word_repository import WordRepository

__all__ = [
    "BaseRepository",
    "SearchRepository",
    "TransferRepository",
    "SiteRepository",
    "RssRepository",
    "BrushRepository",
    "DownloadRepository",
    "SyncRepository",
    "WordRepository",
    "ConfigRepository",
    "PluginRepository",
    "PluginFrameworkRepository",
    "PluginManifestRepositoryAdapter",
    "PluginConfigRepositoryAdapter",
    "PluginLogRepositoryAdapter",
    # RBAC权限管理
    "RBACUserRepository",
    "RBACRoleRepository",
    "RBACPermissionRepository",
    "RBACMenuRepository",
    "RBACLogRepository",
    # API Key
    "APIKeyRepository",
    "APIKeyLogRepository",
    "APIKeyRepositoryAdapter",
    "APIKeyLogRepositoryAdapter",
    # SystemDict
    "SystemDictRepository",
    "SystemDictRepositoryAdapter",
    # RSS Torrent
    "RssTorrentRepositoryAdapter",
    # Media
    "MediaInfoRepository",
    "MediaRecord",
    "MediaInfoRepositoryAdapter",
    # Media Sync
    "MediaSyncRepository",
    "MediaSyncRepositoryAdapter",
]

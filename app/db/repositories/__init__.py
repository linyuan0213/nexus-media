# Repository Layer for Database Operations
# Provides clean separation of data access logic

from .base_repository import BaseRepository
from .search_repository import SearchRepository
from .transfer_repository import TransferRepository
from .site_repository import SiteRepository
from .rss_repository import RssRepository
from .brush_repository import BrushRepository
from .download_repository import DownloadRepository
from .sync_repository import SyncRepository
from .word_repository import WordRepository
from .config_repository import ConfigRepository
from .plugin_repository import PluginRepository
from .plugin_framework_repository import PluginFrameworkRepository
from .plugin_framework_repo_adapter import (
    PluginManifestRepositoryAdapter,
    PluginConfigRepositoryAdapter,
    PluginLogRepositoryAdapter,
)
from .rbac_repository import (
    RBACUserRepository,
    RBACRoleRepository,
    RBACPermissionRepository,
    RBACMenuRepository,
    RBACLogRepository,
)
from .apikey_repository import (
    APIKeyRepository,
    APIKeyLogRepository,
)
from .apikey_repo_adapter import (
    APIKeyRepositoryAdapter,
    APIKeyLogRepositoryAdapter,
)
from .system_dict_repository import SystemDictRepository
from .system_dict_repo_adapter import SystemDictRepositoryAdapter
from .rss_torrent_repo_adapter import RssTorrentRepositoryAdapter

__all__ = [
    'BaseRepository',
    'SearchRepository',
    'TransferRepository',
    'SiteRepository',
    'RssRepository',
    'BrushRepository',
    'DownloadRepository',
    'SyncRepository',
    'WordRepository',
    'ConfigRepository',
    'PluginRepository',
    'PluginFrameworkRepository',
    'PluginManifestRepositoryAdapter',
    'PluginConfigRepositoryAdapter',
    'PluginLogRepositoryAdapter',
    # RBAC权限管理
    'RBACUserRepository',
    'RBACRoleRepository',
    'RBACPermissionRepository',
    'RBACMenuRepository',
    'RBACLogRepository',
    # API Key
    'APIKeyRepository',
    'APIKeyLogRepository',
    'APIKeyRepositoryAdapter',
    'APIKeyLogRepositoryAdapter',
    # SystemDict
    'SystemDictRepository',
    'SystemDictRepositoryAdapter',
    # RSS Torrent
    'RssTorrentRepositoryAdapter',
]
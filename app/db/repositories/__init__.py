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
from .rbac_repository import (
    RBACUserRepository,
    RBACRoleRepository,
    RBACPermissionRepository,
    RBACMenuRepository,
    RBACLogRepository,
)

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
    # RBAC权限管理
    'RBACUserRepository',
    'RBACRoleRepository',
    'RBACPermissionRepository',
    'RBACMenuRepository',
    'RBACLogRepository',
]
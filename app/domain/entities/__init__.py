# coding: utf-8
"""
领域实体导出
"""
from app.domain.entities.site import SiteEntity, SiteStatisticsEntity, SiteSeedingEntity
from app.domain.entities.download import (
    DownloaderEntity,
    DownloadHistoryEntity,
    DownloadSettingEntity,
    IndexerStatisticsEntity,
)
# 注意：config 中的 DownloaderEntity 与 download 中的不同，重命名避免冲突
from app.domain.entities.rss import (
    RssHistoryEntity,
    RssMovieEntity,
    RssTorrentEntity,
    RssTvEntity,
    RssTvEpisodeEntity,
)
from app.domain.entities.transfer import (
    TransferBlacklistEntity,
    TransferHistoryEntity,
    TransferUnknownEntity,
)
from app.domain.entities.brush import BrushTaskEntity, BrushTorrentEntity
from app.domain.entities.sync import SyncPathEntity
from app.domain.entities.config import (
    MessageClientEntity,
    DownloaderEntity as ConfigDownloaderEntity,
    FilterGroupEntity,
    FilterRuleEntity,
    MediaServerEntity,
    TorrentRemoveTaskEntity,
)
from app.domain.entities.rbac import (
    RBACUserEntity,
    RBACRoleEntity,
    RBACPermissionEntity,
    RBACMenuEntity,
    RBACUserLoginLogEntity,
    RBACOperationLogEntity,
)
from app.domain.entities.word import (
    CustomWordEntity,
    CustomWordGroupEntity,
)
from app.domain.entities.plugin import (
    PluginHistoryEntity,
    TmdbBlacklistEntity,
)

__all__ = [
    "SiteEntity",
    "SiteStatisticsEntity",
    "SiteSeedingEntity",
    "DownloaderEntity",
    "DownloadHistoryEntity",
    "DownloadSettingEntity",
    "IndexerStatisticsEntity",
    "RssHistoryEntity",
    "RssMovieEntity",
    "RssTorrentEntity",
    "RssTvEntity",
    "RssTvEpisodeEntity",
    "TransferBlacklistEntity",
    "TransferHistoryEntity",
    "TransferUnknownEntity",
    "BrushTaskEntity",
    "BrushTorrentEntity",
    "SyncPathEntity",
    "MessageClientEntity",
    "ConfigDownloaderEntity",
    "FilterGroupEntity",
    "FilterRuleEntity",
    "MediaServerEntity",
    "TorrentRemoveTaskEntity",
    "RBACUserEntity",
    "RBACRoleEntity",
    "RBACPermissionEntity",
    "RBACMenuEntity",
    "RBACUserLoginLogEntity",
    "RBACOperationLogEntity",
    "CustomWordEntity",
    "CustomWordGroupEntity",
    "PluginHistoryEntity",
    "TmdbBlacklistEntity",
]

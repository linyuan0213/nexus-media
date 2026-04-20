"""
DTO / Schema 定义中心
按业务领域拆分为独立模块，Service 统一从此导入 DTO。
"""

# Media
from .media import (
    MediaInfoResultDTO,
    SeasonEpisodesResultDTO,
    MediaSearchResultDTO,
    TransferHistoryPageDTO,
    UnknownListPageDTO,
    LibrarySpaceDTO,
)

# RSS
from .rss import (
    RssAddResultDTO,
    RssDetailResultDTO,
    RssHistoryResultDTO,
    RssListResultDTO,
    RssIcalResultDTO,
)

# Site
from .site import (
    SiteAttrDTO,
    SiteDetailDTO,
    SiteTestResultDTO,
    SiteHistoryDTO,
    SiteSeedingDTO,
    SiteActivityDTO,
    SiteResourcesResultDTO,
    SiteUpdateResultDTO,
)

# UserRss
from .userrss import (
    UserRssArticleListDTO,
    UserRssHistoryDTO,
    UserRssArticleTestDTO,
    UserRssTaskUpdateDTO,
)

# Brush
from .brush import (
    BrushTaskDTO,
    BrushTorrentListDTO,
)

# Plugin
from .plugin import (
    PluginAppsDTO,
    PluginPageDTO,
    PluginInstallResultDTO,
)

# Download
from .download import (
    Torrent,
    TorrentStatus,
    DownloadResultDTO,
    DownloadingTorrentDTO,
    IndexerStatisticsDTO,
)

# System
from .system import (
    BackupRestoreResultDTO,
    NetTestResultDTO,
    IndexerConfigResultDTO,
    MediaServerConfigResultDTO,
    WebSearchResultDTO,
    VersionInfoDTO,
)

# Sync
from .sync import (
    ManualTransferResultDTO,
    ReIdentifyResultDTO,
)

# Search
from .search import (
    SearchOneMediaResultDTO,
    SearchMediasResultDTO,
)

# Words
from .words import (
    WordGroupDTO,
    WordDTO,
    WordGroupExportDTO,
)

# Indexer
from .indexer import (
    UserIndexerDTO,
    IndexerHashDTO,
    IndexerClientInfoDTO,
    IndexerResourcesResultDTO,
    IndexerSearchResultDTO,
)

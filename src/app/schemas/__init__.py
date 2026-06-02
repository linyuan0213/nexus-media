"""
DTO / Schema 定义中心
按业务领域拆分为独立模块，Service 统一从此导入 DTO。
"""

# Media
# Brush
from .brush import (
    BrushTaskDTO,
    BrushTorrentListDTO,
)

# Download
from .download import (
    DownloadingTorrentDTO,
    DownloadResultDTO,
    IndexerStatisticsDTO,
    Torrent,
    TorrentStatus,
)

# Indexer
from .indexer import (
    IndexerClientInfoDTO,
    IndexerHashDTO,
    IndexerResourcesResultDTO,
    IndexerSearchResultDTO,
    UserIndexerDTO,
)
from .media import (
    LibrarySpaceDTO,
    MediaInfoResultDTO,
    MediaSearchResultDTO,
    SeasonEpisodesResultDTO,
    TransferHistoryPageDTO,
    UnknownListPageDTO,
)

# Plugin
from .plugin import (
    PluginAppsDTO,
    PluginInstallResultDTO,
    PluginPageDTO,
)

# RSS
from .subscribe import (
    SubscribeAddResultDTO,
    SubscribeDetailResultDTO,
    SubscribeHistoryResultDTO,
    SubscribeIcalResultDTO,
    SubscribeListResultDTO,
)

# Search
from .search import (
    SearchMediasResultDTO,
    SearchOneMediaResultDTO,
)

# Site
from .site import (
    SiteActivityDTO,
    SiteAttrDTO,
    SiteDetailDTO,
    SiteHistoryDTO,
    SiteResourcesResultDTO,
    SiteSeedingDTO,
    SiteTestResultDTO,
    SiteUpdateResultDTO,
)

# Sync
from .sync import (
    ManualTransferResultDTO,
    ReIdentifyResultDTO,
)

# System
from .system import (
    BackupRestoreResultDTO,
    IndexerConfigResultDTO,
    MediaServerConfigResultDTO,
    NetTestResultDTO,
    VersionInfoDTO,
    WebSearchResultDTO,
)

# UserRss
from .userrss import (
    UserRssArticleListDTO,
    UserRssArticleTestDTO,
    UserRssHistoryDTO,
    UserRssTaskUpdateDTO,
)

# Words
from .words import (
    WordDTO,
    WordGroupDTO,
    WordGroupExportDTO,
)

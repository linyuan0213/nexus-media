# coding: utf-8
"""
领域接口导出
"""
from app.domain.interfaces.site_repo import (
    ISiteRepository,
    ISiteStatisticsRepository,
    ISiteSeedingRepository,
)
from app.domain.interfaces.download_repo import (
    IDownloadHistoryRepository,
    IDownloadSettingRepository,
    IIndexerStatisticsRepository,
)
from app.domain.interfaces.rss_repo import (
    IRssMovieRepository,
    IRssTvRepository,
    IRssTvEpisodeRepository,
    IRssHistoryRepository,
)
from app.domain.interfaces.transfer_repo import (
    ITransferHistoryRepository,
    ITransferUnknownRepository,
    ITransferBlacklistRepository,
)
from app.domain.interfaces.brush_repo import IBrushTaskRepository, IBrushTorrentRepository

__all__ = [
    "ISiteRepository",
    "ISiteStatisticsRepository",
    "ISiteSeedingRepository",
    "IDownloadHistoryRepository",
    "IDownloadSettingRepository",
    "IIndexerStatisticsRepository",
    "IRssMovieRepository",
    "IRssTvRepository",
    "IRssTvEpisodeRepository",
    "IRssHistoryRepository",
    "ITransferHistoryRepository",
    "ITransferUnknownRepository",
    "ITransferBlacklistRepository",
    "IBrushTaskRepository",
    "IBrushTorrentRepository",
]

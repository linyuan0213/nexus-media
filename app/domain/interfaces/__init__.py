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

__all__ = [
    "ISiteRepository",
    "ISiteStatisticsRepository",
    "ISiteSeedingRepository",
    "IDownloadHistoryRepository",
    "IDownloadSettingRepository",
    "IIndexerStatisticsRepository",
]

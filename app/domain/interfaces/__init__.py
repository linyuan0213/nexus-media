# coding: utf-8
"""
领域接口导出
"""
from app.domain.interfaces.site_repo import (
    ISiteRepository,
    ISiteStatisticsRepository,
    ISiteSeedingRepository,
)

__all__ = [
    "ISiteRepository",
    "ISiteStatisticsRepository",
    "ISiteSeedingRepository",
]

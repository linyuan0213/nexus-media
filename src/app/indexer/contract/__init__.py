"""索引器 provider 稳定契约。"""

from .gateway import IndexerGateway
from .legacy import LegacyClientIndexerProvider, LegacyClientLike
from .models import IndexerHealth, IndexerInfo, IndexerItem, IndexerPage, IndexerQuery, IndexerSite
from .provider import IndexerProvider
from .registry import IndexerProviderRegistry

__all__ = [
    "IndexerGateway",
    "IndexerHealth",
    "IndexerInfo",
    "IndexerItem",
    "IndexerPage",
    "IndexerProvider",
    "IndexerProviderRegistry",
    "IndexerQuery",
    "IndexerSite",
    "LegacyClientIndexerProvider",
    "LegacyClientLike",
]

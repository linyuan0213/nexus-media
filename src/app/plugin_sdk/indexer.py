"""第三方索引器插件 SDK 契约。"""

from app.indexer.contract import (
    IndexerGateway,
    IndexerHealth,
    IndexerInfo,
    IndexerItem,
    IndexerPage,
    IndexerProvider,
    IndexerProviderRegistry,
    IndexerQuery,
    IndexerSite,
    LegacyClientIndexerProvider,
)

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
]

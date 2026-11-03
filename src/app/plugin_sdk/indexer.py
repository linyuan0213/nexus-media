"""第三方索引器插件 SDK 契约。"""

from app.indexer.contract import (
    HttpIndexerProvider,
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
    build_provider,
    load_providers,
    register_provider_factory,
)

__all__ = [
    "build_provider",
    "load_providers",
    "register_provider_factory",
    "HttpIndexerProvider",
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

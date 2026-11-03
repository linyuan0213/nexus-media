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
    build_provider,
    get_global_registry,
    load_providers,
    register_indexer_provider,
    register_provider_factory,
    unregister_plugin_indexers,
)

__all__ = [
    "get_global_registry",
    "register_indexer_provider",
    "unregister_plugin_indexers",
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
]

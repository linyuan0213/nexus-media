"""索引器 provider 稳定契约。"""

from .client_adapter import ClientLike, SiteIndexerProvider
from .factory import build_provider, load_providers, register_provider_factory
from .gateway import IndexerGateway
from .global_registry import (
    get_global_registry,
    register_indexer_provider,
    unregister_plugin_indexers,
)
from .http import HttpIndexerProvider
from .models import IndexerHealth, IndexerInfo, IndexerItem, IndexerPage, IndexerQuery, IndexerSite
from .provider import IndexerProvider
from .registry import IndexerProviderRegistry

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
    "SiteIndexerProvider",
    "ClientLike",
]

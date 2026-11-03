"""索引器 provider 稳定契约。"""

from .crawler import CrawlerIndexerProvider
from .factory import build_provider, load_providers, register_provider_factory
from .gateway import IndexerGateway
from .legacy import LegacyClientIndexerProvider, LegacyClientLike
from .models import IndexerHealth, IndexerInfo, IndexerItem, IndexerPage, IndexerQuery, IndexerSite
from .provider import IndexerProvider
from .registry import IndexerProviderRegistry

__all__ = [
    "build_provider",
    "load_providers",
    "register_provider_factory",
    "CrawlerIndexerProvider",
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

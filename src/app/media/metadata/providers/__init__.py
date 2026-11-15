"""内置 provider 的映射与 adapter."""

from .bangumi import BangumiProvider, bangumi_item_to_record
from .bangumi_discovery import BangumiDiscovery
from .builtin import register_builtin_providers
from .discovery_builtin import register_builtin_discovery_providers
from .douban import DoubanProvider, douban_detail_to_record, parse_runtime, pick_release_date
from .douban_discovery import DoubanDiscovery
from .tmdb import TmdbProvider, tmdb_detail_to_record
from .tmdb_discovery import TmdbDiscovery

__all__ = [
    "BangumiDiscovery",
    "BangumiProvider",
    "DoubanDiscovery",
    "DoubanProvider",
    "TmdbDiscovery",
    "TmdbProvider",
    "bangumi_item_to_record",
    "douban_detail_to_record",
    "parse_runtime",
    "pick_release_date",
    "register_builtin_discovery_providers",
    "register_builtin_providers",
    "tmdb_detail_to_record",
]

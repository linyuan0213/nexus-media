"""内置探索来源注册入口；插件来源继续通过 PluginContext 注册."""

from __future__ import annotations

from typing import Any

from app.media.metadata.registry import MetadataRegistry, registry

from .bangumi_discovery import BangumiDiscovery
from .douban_discovery import DoubanDiscovery
from .tmdb_discovery import TmdbDiscovery


def register_builtin_discovery_providers(
    target: MetadataRegistry | None = None,
    *,
    media_service: Any = None,
    douban: DoubanDiscovery | None = None,
    tmdb: TmdbDiscovery | None = None,
    bangumi: BangumiDiscovery | None = None,
) -> MetadataRegistry:
    """幂等注册内置 discovery provider；已存在的 key 不重复构造."""
    target = target or registry
    if target.get_discovery_provider("douban") is None:
        target.register_discovery_provider(douban or DoubanDiscovery())
    if media_service is not None and target.get_discovery_provider("tmdb") is None:
        target.register_discovery_provider(tmdb or TmdbDiscovery(media_service))
    if target.get_discovery_provider("bangumi") is None:
        target.register_discovery_provider(bangumi or BangumiDiscovery())
    return target

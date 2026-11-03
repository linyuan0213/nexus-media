"""索引器聚合网关：并发调用 provider，去重并保留部分失败信息。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from .models import IndexerHealth, IndexerInfo, IndexerItem, IndexerPage, IndexerQuery
from .registry import IndexerProviderRegistry


class IndexerGateway:
    def __init__(self, registry: IndexerProviderRegistry, *, max_workers: int = 8):
        self._registry = registry
        self._max_workers = max(1, max_workers)

    def search(self, query: IndexerQuery) -> IndexerPage:
        return self._run(query, "search")

    def list(self, query: IndexerQuery) -> IndexerPage:
        return self._run(query, "list")

    def providers(self) -> list[IndexerInfo]:
        return [provider.info() for provider in self._registry.list()]

    def health(self) -> dict[str, IndexerHealth]:
        return {provider.provider_id: provider.health() for provider in self._registry.list()}

    def _run(self, query: IndexerQuery, mode: str) -> IndexerPage:
        query = query.normalized()
        providers = self._registry.list()
        if not providers:
            return IndexerPage(offset=query.offset, limit=query.limit)
        items: list[IndexerItem] = []
        warnings: list[str] = []
        provider_query = IndexerQuery(
            keyword=query.keyword,
            sites=query.sites,
            categories=query.categories,
            media_type=query.media_type,
            content_profile=query.content_profile,
            sort=query.sort,
            offset=0,
            limit=query.offset + query.limit,
            since=query.since,
        )
        with ThreadPoolExecutor(max_workers=min(self._max_workers, len(providers))) as pool:
            futures = {
                pool.submit(provider.search if mode == "search" else provider.list, provider_query): provider
                for provider in providers
            }
            for future in as_completed(futures):
                provider = futures[future]
                try:
                    page = future.result()
                except Exception as exc:  # noqa: BLE001
                    warnings.append(f"{provider.provider_id}: {type(exc).__name__}")
                    continue
                items.extend(page.items)
                warnings.extend(page.warnings)
        deduped: list[IndexerItem] = []
        seen: set[tuple[str, str]] = set()
        for item in items:
            key = (item.site, item.dedup_key)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        total = len(deduped)
        start = query.offset
        page_items = deduped[start : start + query.limit]
        return IndexerPage(
            items=page_items,
            total=total,
            offset=start,
            limit=query.limit,
            has_more=start + len(page_items) < total,
            next_offset=(start + len(page_items)) if start + len(page_items) < total else None,
            warnings=warnings,
        )

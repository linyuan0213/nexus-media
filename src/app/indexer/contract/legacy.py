"""把现有 _IIndexClient 适配成新的 IndexerProvider 契约。"""

from __future__ import annotations

import hashlib
from typing import Any, Protocol

from app.domain.enums import SearchType

from .models import IndexerHealth, IndexerInfo, IndexerItem, IndexerPage, IndexerQuery, IndexerSite


class LegacyClientLike(Protocol):
    client_name: str

    def get_client_id(self) -> str: ...
    def get_status(self) -> bool: ...
    def get_indexers(self, check: bool = True) -> list[Any]: ...
    def search(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]: ...
    def list(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]] | None: ...


class LegacyClientIndexerProvider:
    """兼容层：不重写现有内置/Jackett/Prowlarr 客户端，只统一输入输出。"""

    def __init__(self, client: LegacyClientLike, *, provider_id: str | None = None):
        self._client = client
        self._provider_id = provider_id or client.get_client_id()

    @property
    def provider_id(self) -> str:
        return self._provider_id

    def info(self) -> IndexerInfo:
        sites = [
            IndexerSite(
                id=str(indexer.id or indexer.name),
                name=str(indexer.name),
                public=bool(getattr(indexer, "public", True)),
            )
            for indexer in self._client.get_indexers(check=False) or []
        ]
        return IndexerInfo(
            provider_id=self._provider_id,
            name=getattr(self._client, "client_name", self._provider_id),
            sites=tuple(sites),
            resource_types=("magnet", "ed2k"),
        )

    def health(self) -> IndexerHealth:
        try:
            return IndexerHealth(ok=bool(self._client.get_status()))
        except Exception as exc:  # noqa: BLE001
            return IndexerHealth(ok=False, message=str(exc))

    def search(self, query: IndexerQuery) -> IndexerPage:
        query = query.normalized()
        if not query.keyword:
            return self.list(query)
        return self._query(query, list_mode=False)

    def list(self, query: IndexerQuery) -> IndexerPage:
        query = query.normalized()
        if not query.keyword:
            return self._query(query, list_mode=True)
        return self._query(query, list_mode=False)

    def _query(self, query: IndexerQuery, *, list_mode: bool) -> IndexerPage:
        indexers = self._client.get_indexers(check=True) or []
        if query.sites:
            wanted = {site.lower() for site in query.sites}
            indexers = [
                indexer
                for indexer in indexers
                if str(indexer.name).lower() in wanted or str(indexer.id).lower() in wanted
            ]
        items: list[IndexerItem] = []
        warnings: list[str] = []
        filter_args = {"site": None, "user_id": None}
        for indexer in indexers:
            try:
                if list_mode:
                    raw = self._client.list(
                        index_id=str(indexer.id or indexer.name),
                        page=0,
                        page_size=query.offset + query.limit,
                        keyword=None,
                    )
                else:
                    raw = self._client.search(
                        0,
                        indexer,
                        query.keyword or "",
                        filter_args,
                        None,
                        SearchType.WEB,
                    )
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"{indexer.name}: {type(exc).__name__}")
                continue
            for row in raw or []:
                item = self._to_item(indexer, row)
                if item is not None:
                    items.append(item)
        unique: list[IndexerItem] = []
        seen: set[tuple[str, str]] = set()
        for item in items:
            key = (item.site, item.dedup_key)
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        total = len(unique)
        start = query.offset
        page_items = unique[start : start + query.limit]
        return IndexerPage(
            items=page_items,
            total=total,
            offset=query.offset,
            limit=query.limit,
            has_more=start + len(page_items) < total,
            next_offset=(start + len(page_items)) if start + len(page_items) < total else None,
            warnings=warnings,
        )

    def _to_item(self, indexer: Any, row: dict[str, Any]) -> IndexerItem | None:
        title = str(row.get("title") or "").strip()
        enclosure = str(row.get("enclosure") or row.get("download_url") or "").strip()
        magnet = str(row.get("magnet") or "").strip() or None
        ed2k = str(row.get("ed2k") or "").strip() or None
        if not title or not (enclosure or magnet or ed2k):
            return None
        info_hash = str(row.get("info_hash") or "").strip() or None
        item_id = str(row.get("id") or info_hash or "").strip()
        if not item_id:
            item_id = hashlib.sha1(f"{indexer.name}|{title}|{enclosure}".encode()).hexdigest()[:16]
        return IndexerItem(
            provider_id=self._provider_id,
            site=str(indexer.name),
            site_name=str(indexer.name),
            item_id=item_id,
            title=title,
            category=str(row.get("category") or ""),
            size_bytes=_to_int(row.get("size")),
            published_at=str(row.get("pubdate") or row.get("published_at") or ""),
            detail_url=str(row.get("page_url") or row.get("detail_url") or ""),
            download_url=enclosure or magnet or ed2k or "",
            magnet=magnet,
            ed2k=ed2k,
            info_hash=info_hash,
            resource_type="magnet" if magnet or enclosure else "ed2k",
            description=str(row.get("description") or ""),
            seeders=_to_int(row.get("seeders")),
            peers=_to_int(row.get("peers")),
            extra={"source": row.get("_indexer_source", "")},
        )

    def close(self) -> None:
        close = getattr(self._client, "close", None)
        if callable(close):
            close()


def _to_int(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None

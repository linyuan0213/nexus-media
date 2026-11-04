"""把现有 IndexerClientBase 适配成新的 IndexerProvider 契约。"""

from __future__ import annotations

import hashlib
from typing import Any, Protocol

from app.domain.enums import SearchType

from .models import IndexerHealth, IndexerInfo, IndexerItem, IndexerPage, IndexerQuery, IndexerSite


class ClientLike(Protocol):
    client_name: str

    def get_client_id(self) -> str: ...
    def get_status(self) -> bool: ...
    def get_indexers(self, check: bool = True) -> list[Any]: ...
    def search(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]: ...
    def list(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]] | None: ...


def _to_int(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


class SiteIndexerProvider:
    """把单个站点包装成 provider，保留旧站点的并发/站点级过滤。"""

    def __init__(self, client: ClientLike, indexer: Any, order_seq: int = 0):
        self._client = client
        self._indexer = indexer
        self._order_seq = order_seq
        self._provider_id = f"{client.get_client_id()}:{getattr(indexer, 'name', '')}"

    @property
    def provider_id(self) -> str:
        return self._provider_id

    def info(self) -> IndexerInfo:
        name = str(getattr(self._indexer, "name", ""))
        return IndexerInfo(
            provider_id=self._provider_id,
            name=name,
            sites=(IndexerSite(id=str(getattr(self._indexer, "id", "") or name), name=name),),
            resource_types=("magnet", "ed2k"),
        )

    def health(self) -> IndexerHealth:
        return IndexerHealth(ok=True)

    def search(self, query: IndexerQuery) -> IndexerPage:
        query = query.normalized()
        if not query.keyword:
            return self.list(query)
        if not self._site_allowed(query):
            return IndexerPage(offset=query.offset, limit=query.limit)
        try:
            raw = self._client.search(
                self._order_seq,
                self._indexer,
                query.keyword,
                {"site": None, "user_id": None, "content_profile": query.content_profile},
                None,
                SearchType.WEB,
            )
        except Exception as exc:  # noqa: BLE001
            return IndexerPage(warnings=[f"{self.info().name}: {type(exc).__name__}"])
        items = [item for row in raw or [] if (item := _row_to_item(self._provider_id, self._indexer, row))]
        return _page(items, query)

    def list(self, query: IndexerQuery) -> IndexerPage:
        query = query.normalized()
        if not self._site_allowed(query):
            return IndexerPage(offset=query.offset, limit=query.limit)
        indexer_name = str(getattr(self._indexer, "name", ""))
        try:
            raw = self._client.list(
                index_id=str(getattr(self._indexer, "id", "") or indexer_name),
                page=0,
                page_size=query.offset + query.limit,
                keyword=query.keyword,
            )
        except Exception as exc:  # noqa: BLE001
            return IndexerPage(warnings=[f"{indexer_name}: {type(exc).__name__}"])
        items = [item for row in raw or [] if (item := _row_to_item(self._provider_id, self._indexer, row))]
        return _page(items, query)

    def _site_allowed(self, query: IndexerQuery) -> bool:
        if not query.sites:
            return True
        wanted = {site.lower() for site in query.sites}
        name = str(getattr(self._indexer, "name", "")).lower()
        indexer_id = str(getattr(self._indexer, "id", "")).lower()
        return name in wanted or indexer_id in wanted

    def close(self) -> None:
        return None


def _page(items: list[IndexerItem], query: IndexerQuery) -> IndexerPage:
    unique: list[IndexerItem] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (item.site, item.dedup_key)
        if key not in seen:
            seen.add(key)
            unique.append(item)
    start = query.offset
    page_items = unique[start : start + query.limit]
    return IndexerPage(
        items=page_items,
        total=len(unique),
        offset=start,
        limit=query.limit,
        has_more=start + len(page_items) < len(unique),
        next_offset=(start + len(page_items)) if start + len(page_items) < len(unique) else None,
    )


def _row_to_item(provider_id: str, indexer: Any, row: dict[str, Any]) -> IndexerItem | None:
    title = str(row.get("title") or "").strip()
    enclosure = str(row.get("enclosure") or row.get("download_url") or "").strip()
    magnet = str(row.get("magnet") or "").strip() or None
    ed2k = str(row.get("ed2k") or "").strip() or None
    page_url = str(row.get("page_url") or row.get("detail_url") or "").strip()
    # 部分 HTML 站点只提供详情页，下载时才从详情页解析磁力；不能在这里丢弃
    if not title or not (enclosure or magnet or ed2k or page_url):
        return None
    info_hash = str(row.get("info_hash") or "").strip() or None
    item_id = str(row.get("id") or info_hash or "").strip()
    if not item_id:
        item_id = hashlib.sha1(f"{indexer.name}|{title}|{enclosure or page_url}".encode()).hexdigest()[:16]
    return IndexerItem(
        provider_id=provider_id,
        site=str(indexer.name),
        site_name=str(indexer.name),
        item_id=item_id,
        title=title,
        category=str(row.get("category") or ""),
        size_bytes=_to_int(row.get("size")),
        published_at=str(row.get("pubdate") or row.get("published_at") or ""),
        detail_url=page_url,
        download_url=enclosure or magnet or ed2k or "",
        magnet=magnet,
        ed2k=ed2k,
        info_hash=info_hash,
        resource_type="magnet" if magnet or enclosure else "ed2k" if ed2k else "page",
        description=str(row.get("description") or ""),
        seeders=_to_int(row.get("seeders")),
        peers=_to_int(row.get("peers")),
        extra={
            "source": row.get("_indexer_source", ""),
            "uploadvolumefactor": row.get("uploadvolumefactor"),
            "downloadvolumefactor": row.get("downloadvolumefactor"),
            "public": bool(row.get("_indexer_public", getattr(indexer, "public", False))),
            "labels": row.get("labels"),
            "imdbid": row.get("imdbid"),
        },
    )

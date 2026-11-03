"""标准 HTTP 索引器 provider。"""

from __future__ import annotations

from typing import Any

import httpx

from .models import IndexerHealth, IndexerInfo, IndexerItem, IndexerPage, IndexerQuery, IndexerSite


class HttpIndexerProvider:
    """通过标准 /api/indexer/* JSON 契约接入任意远程索引器。"""

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
        provider_id: str = "remote-indexer",
        info_path: str = "/api/indexer/info",
        search_path: str = "/api/indexer/search",
        list_path: str = "/api/indexer/list",
        icon: str = "",
    ):
        self.base_url = base_url.rstrip("/")
        self.provider_id = provider_id
        self._info_path = info_path
        self._search_path = search_path
        self._list_path = list_path
        self._icon = icon
        self._client = client or httpx.Client(
            timeout=timeout,
            headers={"Authorization": f"Bearer {token}"} if token else {},
        )

    def info(self) -> IndexerInfo:
        payload = self._request(self._info_path)
        sites = tuple(
            IndexerSite(
                id=str(site.get("id") or site.get("name") or ""),
                name=str(site.get("name") or site.get("id") or ""),
                public=True,
            )
            for site in payload.get("sites", [])
        )
        return IndexerInfo(
            provider_id=self.provider_id,
            name=str(payload.get("name") or "Remote Indexer"),
            icon=str(payload.get("icon") or self._icon or ""),
            version=str(payload.get("version") or "1"),
            api_version=str(payload.get("api_version") or "1"),
            capabilities=tuple(payload.get("capabilities") or ("search", "list")),
            sites=sites,
            resource_types=tuple(payload.get("resource_types") or ("magnet",)),
        )

    def health(self) -> IndexerHealth:
        try:
            self._request(self._info_path)
            return IndexerHealth(ok=True)
        except Exception as exc:  # noqa: BLE001
            return IndexerHealth(ok=False, message=str(exc))

    def search(self, query: IndexerQuery) -> IndexerPage:
        query = query.normalized()
        params = self._params(query)
        if query.keyword:
            params["keyword"] = query.keyword
        return self._page(self._search_path, params, query)

    def list(self, query: IndexerQuery) -> IndexerPage:
        query = query.normalized()
        return self._page(self._list_path, self._params(query), query)

    def close(self) -> None:
        self._client.close()

    def _page(self, path: str, params: dict[str, Any], query: IndexerQuery) -> IndexerPage:
        payload = self._request(path, params)
        items = [self._to_item(row) for row in payload.get("items", [])]
        return IndexerPage(
            items=[item for item in items if item is not None],
            total=int(payload.get("total") or 0),
            offset=int(payload.get("offset") or query.offset),
            limit=int(payload.get("limit") or query.limit),
            has_more=bool(payload.get("has_more")),
            next_offset=payload.get("next_offset"),
        )

    def _request(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self._client.get(f"{self.base_url}{path}", params=params)
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _params(query: IndexerQuery) -> dict[str, Any]:
        params: dict[str, Any] = {
            "offset": query.offset,
            "limit": query.limit,
            "dedup": True,
        }
        if query.sites:
            params["site"] = query.sites[0]
        return params

    def _to_item(self, row: dict[str, Any]) -> IndexerItem | None:
        title = str(row.get("title") or "").strip()
        if not title:
            return None
        site = str(row.get("site") or "")
        return IndexerItem(
            provider_id=self.provider_id,
            site=site,
            site_name=str(row.get("site_name") or site),
            item_id=str(row.get("item_id") or row.get("info_hash") or ""),
            title=title,
            category=str(row.get("category") or ""),
            size_bytes=_int_or_none(row.get("size_bytes") or row.get("size")),
            published_at=str(row.get("published_at") or row.get("publish_date") or ""),
            detail_url=str(row.get("detail_url") or ""),
            download_url=str(row.get("download_url") or ""),
            magnet=row.get("magnet"),
            ed2k=row.get("ed2k"),
            info_hash=row.get("info_hash"),
            resource_type=str(row.get("resource_type") or "magnet"),
            description=str(row.get("description") or ""),
        )


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None

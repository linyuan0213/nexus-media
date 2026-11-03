"""索引器 provider 的稳定数据契约。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class IndexerQuery:
    keyword: str | None = None
    sites: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    media_type: str | None = None
    content_profile: str | None = None
    sort: str = "published_at:desc"
    offset: int = 0
    limit: int = 100
    since: str | None = None

    def normalized(self) -> IndexerQuery:
        return IndexerQuery(
            keyword=(self.keyword or "").strip() or None,
            sites=tuple(str(site) for site in self.sites if str(site).strip()),
            categories=tuple(str(cat) for cat in self.categories if str(cat).strip()),
            media_type=self.media_type,
            content_profile=self.content_profile,
            sort=self.sort or "published_at:desc",
            offset=max(0, int(self.offset)),
            limit=max(1, min(1000, int(self.limit))),
            since=self.since,
        )


@dataclass(frozen=True)
class IndexerItem:
    provider_id: str
    site: str
    site_name: str
    item_id: str
    title: str
    category: str = ""
    size_bytes: int | None = None
    published_at: str = ""
    detail_url: str = ""
    download_url: str = ""
    magnet: str | None = None
    ed2k: str | None = None
    info_hash: str | None = None
    resource_type: str = "magnet"
    description: str = ""
    seeders: int | None = None
    peers: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def dedup_key(self) -> str:
        return self.info_hash or self.magnet or self.ed2k or self.download_url or self.item_id


@dataclass
class IndexerPage:
    items: list[IndexerItem] = field(default_factory=list)
    total: int = 0
    offset: int = 0
    limit: int = 100
    has_more: bool = False
    next_offset: int | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class IndexerSite:
    id: str
    name: str
    public: bool = True


@dataclass(frozen=True)
class IndexerInfo:
    provider_id: str
    name: str
    icon: str = ""
    version: str = "1"
    api_version: str = "1"
    capabilities: tuple[str, ...] = ("search", "list")
    sites: tuple[IndexerSite, ...] = ()
    resource_types: tuple[str, ...] = ("magnet",)


@dataclass(frozen=True)
class IndexerHealth:
    ok: bool
    message: str = ""

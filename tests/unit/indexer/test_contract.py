"""索引器 provider 契约和适配器测试。"""

from types import SimpleNamespace

import pytest

from app.indexer.contract import (
    IndexerGateway,
    IndexerProviderRegistry,
    IndexerQuery,
    LegacyClientIndexerProvider,
)


class FakeClient:
    client_name = "Fake"

    def __init__(self):
        self.indexers = [
            SimpleNamespace(id="site-a", name="Site A", public=True),
            SimpleNamespace(id="site-b", name="Site B", public=False),
        ]
        self.last_error = ""

    def get_client_id(self):
        return "fake"

    def get_status(self):
        return True

    def get_indexers(self, check=True):
        return self.indexers

    def search(self, order_seq, indexer, keyword, filter_args, match_media, in_from):
        return [
            {
                "title": f"{indexer.name} {keyword}",
                "enclosure": f"magnet:?xt=urn:btih:{indexer.id}",
                "size": "1024",
                "_indexer_name": indexer.name,
                "_indexer_source": "fake",
                "page_url": f"https://example/{indexer.id}",
            },
            {
                "title": f"{indexer.name} {keyword}",
                "enclosure": f"magnet:?xt=urn:btih:{indexer.id}",
                "size": "1024",
                "_indexer_name": indexer.name,
            },
        ]

    def list(self, index_id, page=0, page_size=100, keyword=None):
        return [
            {
                "title": f"{index_id} latest",
                "enclosure": f"https://example/{index_id}.torrent",
                "size": 2048,
                "_indexer_name": index_id,
            }
        ]

    def close(self):
        pass


def test_legacy_provider_normalizes_search_and_dedup():
    provider = LegacyClientIndexerProvider(FakeClient())
    page = provider.search(IndexerQuery(keyword="demo", limit=10))
    assert page.total == 2
    assert page.items[0].site in {"Site A", "Site B"}
    assert page.items[0].provider_id == "fake"
    assert page.items[0].download_url.startswith("magnet:")
    assert page.items[0].size_bytes == 1024
    assert page.items[0].item_id
    assert len({(item.site, item.dedup_key) for item in page.items}) == 2


def test_legacy_provider_list_and_site_filter():
    provider = LegacyClientIndexerProvider(FakeClient())
    page = provider.list(IndexerQuery(sites=("Site A",), limit=10))
    assert page.total == 1
    assert page.items[0].site == "Site A"
    assert page.items[0].download_url.endswith(".torrent")


def test_registry_rejects_duplicate_and_unregisters():
    registry = IndexerProviderRegistry()
    provider = LegacyClientIndexerProvider(FakeClient())
    registry.register(provider)
    assert registry.get("fake") is provider
    with pytest.raises(ValueError):
        registry.register(provider)
    registry.unregister("fake")
    assert registry.get("fake") is None


class BrokenProvider:
    provider_id = "broken"

    def info(self):
        raise AssertionError("not used")

    def health(self):
        raise AssertionError("not used")

    def search(self, query):
        raise RuntimeError("down")

    def list(self, query):
        raise RuntimeError("down")

    def close(self):
        pass


def test_gateway_keeps_partial_results_and_warnings():
    registry = IndexerProviderRegistry()
    registry.register(LegacyClientIndexerProvider(FakeClient()))
    registry.register(BrokenProvider())
    page = IndexerGateway(registry).search(IndexerQuery(keyword="demo", limit=10))
    assert len(page.items) == 2
    assert any("broken" in warning for warning in page.warnings)


def test_list_and_gateway_apply_offset_once():
    provider = LegacyClientIndexerProvider(FakeClient())
    page = provider.list(IndexerQuery(offset=1, limit=1))
    assert page.total == 2
    assert len(page.items) == 1
    assert page.items[0].site == "Site B"

    registry = IndexerProviderRegistry()
    registry.register(provider)
    gateway_page = IndexerGateway(registry).list(IndexerQuery(offset=1, limit=1))
    assert len(gateway_page.items) == 1
    assert gateway_page.offset == 1


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeHttpClient:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None):
        self.calls.append((url, params))
        if url.endswith("/api/indexer/info"):
            return FakeResponse(
                {
                    "name": "Crawler",
                    "version": "1.0",
                    "capabilities": ["search", "list"],
                    "sites": [{"id": "site-a", "name": "Site A"}],
                    "resource_types": ["magnet"],
                }
            )
        return FakeResponse(
            {
                "total": 25,
                "offset": 10,
                "limit": 10,
                "has_more": True,
                "next_offset": 20,
                "items": [
                    {
                        "item_id": "1",
                        "site": "site-a",
                        "site_name": "Site A",
                        "title": "Demo",
                        "size": 1024,
                        "download_url": "magnet:?xt=urn:btih:abc",
                        "magnet": "magnet:?xt=urn:btih:abc",
                        "resource_type": "magnet",
                    }
                ],
            }
        )


def test_crawler_provider_maps_search_list_and_info():
    from typing import Any, cast

    from app.indexer.contract import HttpIndexerProvider

    http = FakeHttpClient()
    provider = HttpIndexerProvider("http://crawler", provider_id="http-test", client=cast(Any, http))
    info = provider.info()
    assert info.provider_id == "http-test"
    assert info.sites[0].name == "Site A"

    page = provider.search(IndexerQuery(keyword="demo", offset=10, limit=10))
    assert page.total == 25
    assert page.has_more is True
    assert page.items[0].item_id == "1"
    assert http.calls[-1][1]["keyword"] == "demo"

    provider.list(IndexerQuery(offset=0, limit=20))
    assert http.calls[-1][0].endswith("/api/indexer/list")
    assert http.calls[-1][1]["limit"] == 20


def test_provider_factory_loads_multiple_instances():
    from app.indexer.contract import IndexerProviderRegistry, load_providers

    registry = IndexerProviderRegistry()
    load_providers(
        registry,
        [
            {"id": "indexer-home", "type": "http", "base_url": "http://home"},
            {"id": "indexer-vps", "type": "http", "base_url": "http://vps"},
        ],
    )
    assert registry.get("indexer-home") is not None
    assert registry.get("indexer-vps") is not None


def test_external_provider_item_converts_to_pipeline_raw():
    from app.indexer.contract import IndexerItem
    from app.indexer.indexer import Indexer

    raw = Indexer._external_to_raw(
        IndexerItem(
            provider_id="crawler-a",
            site="site-a",
            site_name="Site A",
            item_id="1",
            title="Demo",
            download_url="magnet:?xt=urn:btih:abc",
            size_bytes=1024,
        )
    )
    assert raw["enclosure"].startswith("magnet:")
    assert raw["_indexer_source"] == "crawler-a"
    assert raw["_indexer_name"] == "Site A"

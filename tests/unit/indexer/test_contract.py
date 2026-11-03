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

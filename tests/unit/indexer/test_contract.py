"""索引器 provider 契约和适配器测试。"""

from types import SimpleNamespace

import pytest

from app.indexer.contract import (
    IndexerGateway,
    IndexerProviderRegistry,
    IndexerQuery,
    SiteIndexerProvider,
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


def make_provider(site_name: str = "Site A"):
    client = FakeClient()
    indexer = next(item for item in client.indexers if item.name == site_name)
    return SiteIndexerProvider(client, indexer)


def test_site_provider_normalizes_search_and_dedup():
    provider = make_provider()
    page = provider.search(IndexerQuery(keyword="demo", limit=10))
    assert page.total == 1
    assert page.items[0].site == "Site A"
    assert page.items[0].provider_id == "fake:Site A"
    assert page.items[0].download_url.startswith("magnet:")
    assert page.items[0].size_bytes == 1024
    assert page.items[0].item_id


def test_site_provider_list_and_site_filter():
    provider = make_provider()
    page = provider.list(IndexerQuery(sites=("Site A",), limit=10))
    assert page.total == 1
    assert page.items[0].site == "Site A"
    assert page.items[0].download_url.endswith(".torrent")


def test_registry_rejects_duplicate_and_unregisters():
    registry = IndexerProviderRegistry()
    provider = make_provider()
    registry.register(provider)
    assert registry.get("fake:Site A") is provider
    with pytest.raises(ValueError):
        registry.register(provider)
    registry.unregister("fake:Site A")
    assert registry.get("fake:Site A") is None


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
    registry.register(make_provider())
    registry.register(BrokenProvider())
    page = IndexerGateway(registry).search(IndexerQuery(keyword="demo", limit=10))
    assert len(page.items) == 1
    assert any("broken" in warning for warning in page.warnings)


def test_list_and_gateway_apply_offset_once():
    registry = IndexerProviderRegistry()
    registry.register(make_provider("Site A"))
    registry.register(make_provider("Site B"))
    gateway_page = IndexerGateway(registry).list(IndexerQuery(offset=1, limit=1))
    assert len(gateway_page.items) == 1
    assert gateway_page.offset == 1
    assert gateway_page.items[0].site == "Site B"


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

    raw = Indexer._provider_to_raw(
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
    assert raw["_indexer_name"] == "site-a"
    assert raw["_indexer_display_name"] == "Site A"


def test_global_registry_tracks_plugin_owner():
    from app.indexer.contract import (
        get_global_registry,
        register_indexer_provider,
        unregister_plugin_indexers,
    )

    provider = make_provider()
    register_indexer_provider(provider, "plugin-x")
    assert get_global_registry().get("fake:Site A") is provider
    unregister_plugin_indexers("plugin-x")
    assert get_global_registry().get("fake:Site A") is None


def test_plugin_manifest_parses_indexer_providers():
    from app.schemas.plugin import PluginManifest

    manifest = PluginManifest.from_dict(
        {
            "id": "indexer-plugin",
            "name": "Indexer",
            "backend": {"metadata": {"indexer_providers": [{"key": "my-indexer", "type": "http"}]}},
        }
    )
    assert manifest.backend.metadata.keys("indexer_providers") == {"my-indexer"}


class SlowProvider:
    provider_id = "slow"

    def __init__(self, seconds: float = 2.0):
        self._seconds = seconds

    def info(self):
        raise AssertionError("not used")

    def health(self):
        raise AssertionError("not used")

    def search(self, query):
        import time

        time.sleep(self._seconds)
        return IndexerPageStub()

    def list(self, query):
        return self.search(query)

    def close(self):
        pass


class IndexerPageStub:
    items = []
    warnings = []


def test_gateway_times_out_slow_provider_and_keeps_fast_results():
    import time

    registry = IndexerProviderRegistry()
    registry.register(make_provider())
    registry.register(SlowProvider(seconds=5))
    started = time.monotonic()
    page = IndexerGateway(registry, provider_timeout=0.3).search(IndexerQuery(keyword="demo", limit=10))
    elapsed = time.monotonic() - started

    assert elapsed < 2
    assert len(page.items) == 1
    assert any("slow" in warning and "timeout" in warning for warning in page.warnings)


def test_provider_to_raw_keeps_promotion_and_public_flag():
    from app.indexer.contract import IndexerItem
    from app.indexer.indexer import Indexer

    item = IndexerItem(
        provider_id="builtin:Site A",
        site="Site A",
        site_name="Site A",
        item_id="1",
        title="demo",
        download_url="magnet:?xt=urn:btih:abc",
        extra={
            "public": True,
            "uploadvolumefactor": 2.0,
            "downloadvolumefactor": 0.0,
            "labels": ["免费"],
            "imdbid": "tt123",
        },
    )
    raw = Indexer._provider_to_raw(item)

    assert raw["_indexer_public"] is True
    assert raw["uploadvolumefactor"] == 2.0
    assert raw["downloadvolumefactor"] == 0.0
    assert raw["labels"] == ["免费"]
    assert raw["imdbid"] == "tt123"


def test_site_indexer_provider_keeps_promotion_fields():
    class PromotionClient(FakeClient):
        def search(self, order_seq, indexer, keyword, filter_args, match_media, in_from):
            return [
                {
                    "title": f"{indexer.name} free",
                    "enclosure": "magnet:?xt=urn:btih:free",
                    "size": "2048",
                    "uploadvolumefactor": 2.0,
                    "downloadvolumefactor": 0.0,
                    "_indexer_public": True,
                    "labels": ["2x免费"],
                }
            ]

    client = PromotionClient()
    provider = SiteIndexerProvider(client, client.indexers[0])
    page = provider.search(IndexerQuery(keyword="demo", limit=10))

    assert len(page.items) == 1
    extra = page.items[0].extra
    assert extra["public"] is True
    assert extra["uploadvolumefactor"] == 2.0
    assert extra["downloadvolumefactor"] == 0.0
    assert extra["labels"] == ["2x免费"]


def test_http_provider_passes_only_matching_site():
    from typing import Any, cast

    from app.indexer.contract import HttpIndexerProvider

    http = FakeHttpClient()
    provider = HttpIndexerProvider("http://crawler", provider_id="http-test", client=cast(Any, http))
    page = provider.search(IndexerQuery(keyword="demo", sites=("Site A",)))

    assert len(page.items) == 1
    assert page.items[0].extra["public"] is True
    assert http.calls[-1][1]["site"] == "Site A"


def test_http_provider_skips_search_when_site_not_owned():
    from typing import Any, cast

    from app.indexer.contract import HttpIndexerProvider

    http = FakeHttpClient()
    provider = HttpIndexerProvider("http://crawler", provider_id="http-test", client=cast(Any, http))
    page = provider.search(IndexerQuery(keyword="demo", sites=("Other Site",)))

    assert page.items == []
    assert not any(call[0].endswith("/api/indexer/search") for call in http.calls)


def test_site_provider_keeps_detail_only_rows():
    class DetailOnlyClient(FakeClient):
        def search(self, order_seq, indexer, keyword, filter_args, match_media, in_from):
            return [
                {
                    "title": "DEMO-252",
                    "page_url": "https://example.test/torrent/252",
                    "size": "1024",
                }
            ]

    client = DetailOnlyClient()
    provider = SiteIndexerProvider(client, client.indexers[0])
    page = provider.search(IndexerQuery(keyword="DEMO-252", limit=10))

    assert len(page.items) == 1
    item = page.items[0]
    assert item.download_url == ""
    assert item.detail_url == "https://example.test/torrent/252"
    assert item.resource_type == "page"


def test_provider_to_raw_keeps_indexer_order_and_source():
    from app.indexer.contract import IndexerItem
    from app.indexer.indexer import Indexer

    item = IndexerItem(
        provider_id="builtin:Site A",
        site="Site A",
        site_name="Site A",
        item_id="1",
        title="demo",
        download_url="magnet:?xt=urn:btih:abc",
        priority=3,
        extra={"source": "builtin"},
    )
    raw = Indexer._provider_to_raw(item)

    assert raw["_indexer_source"] == "builtin"
    assert raw["_indexer_order"] == 9996


def test_dedup_prefers_configured_priority_then_builtin_tie():
    from app.indexer.indexer import Indexer

    results = [
        {"title": "demo", "size": 1, "_indexer_source": "builtin", "_indexer_order": 50},
        {"title": "demo", "size": 1, "_indexer_source": "http-indexer", "_indexer_order": 90},
    ]
    deduped = Indexer._dedup(results)
    assert deduped[0]["_indexer_source"] == "http-indexer"

    tie = [
        {"title": "demo", "size": 1, "_indexer_source": "http-indexer", "_indexer_order": 90},
        {"title": "demo", "size": 1, "_indexer_source": "builtin", "_indexer_order": 90},
    ]
    assert Indexer._dedup(tie)[0]["_indexer_source"] == "builtin"


def test_priority_provider_injects_site_priority():
    from typing import Any, cast

    from app.indexer.contract import HttpIndexerProvider, PriorityProvider

    http = FakeHttpClient()
    provider = HttpIndexerProvider("http://crawler", provider_id="http-test", client=cast(Any, http))
    wrapped = PriorityProvider(provider, {"site-a": 10})
    page = wrapped.search(IndexerQuery(keyword="demo", sites=("Site A",)))

    assert page.items[0].priority == 10
    assert wrapped.info().sites[0].priority == 10

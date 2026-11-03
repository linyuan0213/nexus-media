"""Jackett/Prowlarr 共享 Torznab 基类测试。"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.domain.enums import SearchType
from app.indexer.client._torznab import TorznabIndexerClient
from app.indexer.client.jackett import Jackett
from app.indexer.client.prowlarr import Prowlarr


class DummyTorznab(TorznabIndexerClient):
    client_id = "dummy"
    client_type = "dummy"
    client_name = "Dummy"
    index_type = "Dummy"
    host = "http://example/"
    api_key = "key"

    def __init__(self):
        super().__init__()
        self.fetch_count = 0
        self.list_args = None

    @classmethod
    def match(cls, ctype):
        return ctype == cls.client_id

    def get_type(self):
        return self.client_type

    def get_client_id(self):
        return self.client_id

    def _fetch_indexers(self):
        self.fetch_count += 1
        return [SimpleNamespace(id="site-1", name="Site 1", public=True)]

    def _search_items(self, indexer, keyword):
        return [{"title": f"{keyword}-{index}", "enclosure": f"magnet:?xt=urn:btih:{index}"} for index in range(25)]

    def _list_items(self, indexer, keyword, offset, limit):
        self.list_args = (offset, limit)
        return [{"title": f"item-{index}", "enclosure": f"magnet:?xt=urn:btih:{index}"} for index in range(25)][
            offset : offset + limit
        ]


def test_base_caches_indexers_and_injects_meta():
    client = DummyTorznab()
    assert client.get_status() is True
    assert client.get_status() is True
    assert client.fetch_count == 1
    items = client.search(1, client.get_indexers()[0], "demo", {}, None, SearchType.WEB)
    assert len(items) == 25
    assert items[0]["_indexer_name"] == "Site 1"
    assert client.last_error == ""


def test_base_list_honors_page_and_page_size():
    client = DummyTorznab()
    client.get_indexers()
    items = client.list("site-1", page=1, page_size=10)
    assert client.list_args == (10, 10)
    assert items is not None
    assert len(items) == 10
    assert items[0]["title"] == "item-10"


def test_jackett_list_honors_page_size():
    client = Jackett({"host": "http://jackett/", "api_key": "key"})
    client._indexer_cache = [SimpleNamespace(id="site-1", name="Site 1", public=True)]
    client._indexer_cache_at = float("inf")
    response = Mock()
    response.json.return_value = {
        "Results": [{"Title": f"T{index}", "Link": f"https://x/{index}.torrent", "Size": 1} for index in range(25)]
    }
    with patch("app.indexer.client.jackett.HttpClient.get", return_value=response):
        items = client.list("site-1", page=1, page_size=10)
    assert items is not None
    assert len(items) == 10
    assert items[0]["title"] == "T10"


def test_prowlarr_list_passes_offset_and_limit():
    client = Prowlarr({"host": "http://prowlarr/", "api_key": "key"})
    indexer = SimpleNamespace(id="site-1", name="Site 1", domain="http://prowlarr/1/api")
    client._indexer_cache = [indexer]
    client._indexer_cache_at = float("inf")
    captured = {}

    def parse(url):
        captured["url"] = url
        return []

    with patch.object(client, "_parse_torznabxml", side_effect=parse):
        client.list("site-1", page=1, page_size=10)
    assert "offset=10" in captured["url"]
    assert "limit=10" in captured["url"]

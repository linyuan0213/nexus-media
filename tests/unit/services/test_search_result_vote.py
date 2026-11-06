"""搜索结果评分补全测试."""

from types import SimpleNamespace

from app.services.search_result_service import SearchResultService


class _Gateway:
    def __init__(self):
        self.calls = 0

    def lookup(self, provider, external_id, **kwargs):
        self.calls += 1
        return {"ratings": {"douban": 8.1}}


def test_resolve_vote_fills_missing_provider_rating():
    gateway = _Gateway()
    service = SearchResultService(media_server=None, subscribe=None, metadata_gateway=gateway)  # type: ignore[arg-type]
    item = SimpleNamespace(
        VOTE="0",
        ANCHOR_PROVIDER="douban",
        ANCHOR_EXTERNAL_ID="37923549",
        TYPE="anime",
    )
    cache = {}
    assert service._resolve_vote(item, cache) == "8.1"
    assert service._resolve_vote(item, cache) == "8.1"
    assert gateway.calls == 1


def test_resolve_vote_keeps_existing_rating():
    service = SearchResultService(media_server=None, subscribe=None, metadata_gateway=None)  # type: ignore[arg-type]
    item = SimpleNamespace(VOTE="7.5", ANCHOR_PROVIDER="douban", ANCHOR_EXTERNAL_ID="1", TYPE="movie")
    assert service._resolve_vote(item, {}) == "7.5"

"""Agent media handlers 单元测试."""

from unittest.mock import MagicMock

import pytest

from app.agent.tools.handlers_media import _search_cache, media_search


@pytest.fixture
def deps():
    _search_cache.clear()
    intent = MagicMock()
    intent.ready = False
    deps = {
        "search_intent_agent": intent,
        "media_service": MagicMock(),
        "indexer_service": MagicMock(),
    }
    return deps


class TestMediaSearch:
    def _setup(self, deps):
        media_info = MagicMock()
        media_info.title = "Test Movie"
        deps["media_service"].get_media_info.return_value = media_info
        result = MagicMock()
        result.title = "Test Movie 2024"
        result.org_string = "Test Movie 2024"
        result.site = "s1"
        result.size = "5GB"
        result.seeders = 10
        result.enclosure = "magnet:1"
        deps["indexer_service"].search_by_keyword.return_value = [result]
        return media_info

    def test_media_search_caches_result(self, deps):
        self._setup(deps)
        r1 = media_search(deps, query="test", media_type="movie")
        r2 = media_search(deps, query="test", media_type="movie")
        assert r1.success is True
        assert r2.success is True
        deps["indexer_service"].search_by_keyword.assert_called_once()

    def test_media_search_different_params_not_cached(self, deps):
        self._setup(deps)
        media_search(deps, query="test", media_type="movie")
        media_search(deps, query="test", media_type="tv")
        assert deps["indexer_service"].search_by_keyword.call_count == 2

    def test_media_search_no_results(self, deps):
        media_info = MagicMock()
        media_info.title = "Unknown"
        deps["media_service"].get_media_info.return_value = media_info
        deps["indexer_service"].search_by_keyword.return_value = []
        result = media_search(deps, query="unknown")
        assert result.success is True
        assert "未找到" in result.data

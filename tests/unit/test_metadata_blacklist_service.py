"""MetadataBlacklistService 单元测试."""

from unittest.mock import MagicMock, patch

import pytest

from app.domain.media_types import ProviderMediaType
from app.services.metadata_blacklist_service import MetadataBlacklistService


class _BlackItem:
    ID: int = 1
    PROVIDER: str = "tmdb"
    EXTERNAL_ID: int = 123
    MEDIA_TYPE: str = "movie"
    TITLE: str = "Test Movie"
    YEAR: str = "2024"
    POSTER_PATH: str = "/poster.jpg"
    BACKDROP_PATH: str = "/bg.jpg"
    NOTE: str = "note"


@pytest.fixture
def mock_gateway():
    return MagicMock()


@pytest.fixture
def mock_repo():
    return MagicMock()


@pytest.fixture
def service(mock_gateway, mock_repo):
    with patch("app.services.metadata_blacklist_service.get_cache_manager") as mock_cache_mgr:
        cache = MagicMock()
        cache.get.return_value = None
        mock_cache_mgr.return_value.get_or_create.return_value = cache
        svc = MetadataBlacklistService(
            metadata_gateway=mock_gateway,
            metadata_blacklist_repo=mock_repo,
        )
        svc._cache = cache
        yield svc


class TestMetadataBlacklistService:
    def test_is_blacklisted(self, service, mock_repo):
        mock_repo.is_blacklisted.return_value = True
        assert service.is_blacklisted(123, "movie") is True
        mock_repo.is_blacklisted.assert_called_once_with("tmdb", 123, "movie")

    def test_get_blacklist_pagination(self, service, mock_repo):
        mock_repo.get_blacklist.return_value = [_BlackItem()]
        items, total = service.get_blacklist(page=1, count=10)
        assert total == 1
        assert items[0]["title"] == "Test Movie"
        assert items[0]["media_type"] == ProviderMediaType.MOVIE.value
        assert items[0]["media_type_label"] == ProviderMediaType.MOVIE.display_name
        service._cache.set.assert_called_once()

    def test_get_blacklist_filter_by_external_id(self, service, mock_repo):
        item1 = _BlackItem()
        item1.EXTERNAL_ID = 123
        item2 = _BlackItem()
        item2.EXTERNAL_ID = 456
        mock_repo.get_blacklist.return_value = [item1, item2]
        items, total = service.get_blacklist(external_id=456)
        assert total == 1
        assert len(items) == 1
        assert items[0]["external_id"] == "456"
        assert items[0]["provider"] == "tmdb"

    def test_get_blacklist_cache_hit(self, service, mock_repo):
        cached = [_BlackItem()]
        service._cache.get.return_value = cached
        items, total = service.get_blacklist()
        assert total == 1
        mock_repo.get_blacklist.assert_not_called()

    def test_add_to_blacklist(self, service, mock_gateway, mock_repo):
        mock_gateway.details.return_value = {
            "title": "Test",
            "name": "Test",
            "poster_path": "/p.jpg",
            "backdrop_path": "/b.jpg",
        }
        with patch("app.services.metadata_blacklist_service.meta_info") as mock_meta:
            mi = MagicMock()
            mi.title = "Test"
            mi.year = "2024"
            mi.poster_path = "/p.jpg"
            mi.backdrop_path = "/b.jpg"
            mi.note = ""
            mock_meta.return_value = mi
            service.add_to_blacklist(123, "movie")
            mock_repo.insert_blacklist.assert_called_once()
            service._cache.clear.assert_called_once()

    def test_add_to_blacklist_missing_info(self, service, mock_gateway):
        mock_gateway.details.return_value = None
        with pytest.raises(ValueError):
            service.add_to_blacklist(123, "movie")

    def test_remove_from_blacklist(self, service, mock_repo):
        service.remove_from_blacklist(123, "movie")
        mock_repo.delete_blacklist.assert_called_once_with("tmdb", 123, "movie")
        service._cache.clear.assert_called_once()

    def test_clear_blacklist(self, service, mock_repo):
        service.clear_blacklist()
        mock_repo.clear_blacklist.assert_called_once_with(None)
        service._cache.clear.assert_called_once()

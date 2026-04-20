# -*- coding: utf-8 -*-
"""
SearchService 单元测试
"""
from unittest.mock import MagicMock, patch

import pytest

from app.schemas.search import SearchOneMediaResultDTO, SearchMediasResultDTO
from app.services.search_service import SearchService
from app.utils.types import SearchType


@pytest.fixture
def mock_searcher():
    return MagicMock()


@pytest.fixture
def mock_downloader():
    return MagicMock()


@pytest.fixture
def mock_media():
    return MagicMock()


@pytest.fixture
def svc(mock_searcher, mock_downloader, mock_media):
    return SearchService(
        searcher=mock_searcher,
        downloader=mock_downloader,
        media=mock_media
    )


class TestSearchMedias:
    def test_empty_keyword(self, svc):
        result = svc.search_medias("", {})
        assert result.results == []

    def test_success(self, svc, mock_searcher):
        mock_searcher.search_medias.return_value = [{"title": "A"}]
        result = svc.search_medias("test", {}, in_from=SearchType.WEB)
        assert len(result.results) == 1
        assert result.results[0]["title"] == "A"


class TestSearchOneMedia:
    def test_success(self, svc, mock_searcher):
        mock_searcher.search_one_media.return_value = (
            MagicMock(), {"left": True}, 5, 3
        )
        media = MagicMock()
        result = svc.search_one_media(
            media_info=media,
            in_from=SearchType.RSS,
            no_exists={},
            sites=["s1"],
            filters={"restype": "BluRay"},
            user_name="user"
        )
        assert isinstance(result, SearchOneMediaResultDTO)
        assert result.total_count == 5
        assert result.download_count == 3
        assert result.no_exists == {"left": True}

    def test_none_result(self, svc, mock_searcher):
        mock_searcher.search_one_media.return_value = None
        result = svc.search_one_media(
            media_info=MagicMock(),
            in_from=SearchType.WEB,
            no_exists={}
        )
        assert result.total_count == 0
        assert result.download_count == 0


class TestSearchResultsManagement:
    def test_get_by_id(self, svc, mock_searcher):
        mock_searcher.get_search_result_by_id.return_value = {"id": 1}
        assert svc.get_search_result_by_id(1) == {"id": 1}

    def test_get_all(self, svc, mock_searcher):
        mock_searcher.get_search_results.return_value = [{"id": 1}]
        assert svc.get_search_results() == [{"id": 1}]

    def test_delete_all(self, svc, mock_searcher):
        svc.delete_all_search_torrents()
        mock_searcher.delete_all_search_torrents.assert_called_once()

    def test_insert(self, svc, mock_searcher):
        svc.insert_search_results([{"t": 1}], title="test")
        mock_searcher.insert_search_results.assert_called_once_with(
            [{"t": 1}], "test", True
        )


class TestBuildSearchNames:
    def test_keyword_direct(self, svc):
        media = MagicMock()
        media.keyword = "direct"
        media.cn_name = None
        names = svc.build_search_names(media)
        assert names == ["direct"]

    def test_basic_names(self, svc):
        media = MagicMock()
        media.keyword = None
        media.cn_name = "中文"
        media.title = "Title"
        media.en_name = "English"
        media.original_language = "en"
        media.original_title = "Orig"
        media.tmdb_zhtw_title = None
        names = svc.build_search_names(media)
        assert "中文" in names
        assert "English" in names

    def test_multi_language(self, svc, mock_media):
        media = MagicMock()
        media.keyword = None
        media.cn_name = "中文"
        media.title = "Title"
        media.en_name = "English"
        media.original_language = "ja"
        media.original_title = "Orig"
        mock_media.get_tmdb_zhtw_title.return_value = "繁體"
        mock_media.get_tmdb_en_title.return_value = "English"

        with patch.object(svc, '_media', mock_media):
            with patch('config.Config') as MockConfig:
                MockConfig().get_config.return_value = {"search_multi_language": True}
                names = svc.build_search_names(media)
                assert "繁體" in names
                assert "Orig" in names

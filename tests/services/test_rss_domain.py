# -*- coding: utf-8 -*-
"""
RSS领域层单元测试
测试RssMovie/Tv/History实体和适配器
"""
import pytest
from unittest.mock import MagicMock

from app.domain.entities.rss import (
    RssHistoryEntity,
    RssMovieEntity,
    RssTvEntity,
    RssTvEpisodeEntity,
)
from app.db.repositories.rss_repo_adapter import (
    RssMovieRepositoryAdapter,
    RssTvRepositoryAdapter,
    RssTvEpisodeRepositoryAdapter,
    RssHistoryRepositoryAdapter,
)


class TestRssMovieEntity:
    def test_from_orm_success(self):
        mock = MagicMock()
        mock.ID = 1
        mock.NAME = "Test Movie"
        mock.YEAR = "2023"
        mock.TMDBID = "123"
        mock.STATE = "D"
        mock.OVER_EDITION = 1
        mock.FUZZY_MATCH = 0
        entity = RssMovieEntity.from_orm(mock)
        assert entity.name == "Test Movie"
        assert entity.over_edition is True
        assert entity.fuzzy_match is False

    def test_from_orm_none(self):
        assert RssMovieEntity.from_orm(None) is None

    def test_to_dict(self):
        entity = RssMovieEntity(
            id=1, name="Test", year="2023", keyword="", tmdb_id="123",
            image="", rss_sites="", search_sites="", over_edition=False,
            filter_order=0, filter_restype="", filter_pix="", filter_rule=0,
            filter_team="", filter_include="", filter_exclude="", save_path="",
            download_setting=None, fuzzy_match=False, state="D", description="", note=""
        )
        d = entity.to_dict()
        assert d["name"] == "Test"
        assert d["state"] == "D"


class TestRssTvEntity:
    def test_from_orm_success(self):
        mock = MagicMock()
        mock.ID = 1
        mock.NAME = "Test TV"
        mock.SEASON = "S01"
        mock.TOTAL_EP = 10
        mock.CURRENT_EP = 5
        mock.LACK = 3
        entity = RssTvEntity.from_orm(mock)
        assert entity.name == "Test TV"
        assert entity.season == "S01"
        assert entity.total_ep == 10

    def test_to_dict(self):
        entity = RssTvEntity(
            id=1, name="Test", year="2023", keyword="", season="S01", tmdb_id="",
            image="", rss_sites="", search_sites="", over_edition=False,
            filter_order=0, filter_restype="", filter_pix="", filter_rule=0,
            filter_team="", filter_include="", filter_exclude="", save_path="",
            download_setting=None, fuzzy_match=False, total_ep=10, current_ep=5,
            total=10, lack=3, state="D", description="", note=""
        )
        d = entity.to_dict()
        assert d["lack"] == 3


class TestRssHistoryEntity:
    def test_from_orm(self):
        mock = MagicMock()
        mock.ID = 1
        mock.TYPE = "MOV"
        mock.RSSID = "rss1"
        mock.NAME = "History"
        entity = RssHistoryEntity.from_orm(mock)
        assert entity.rss_type == "MOV"
        assert entity.name == "History"


class TestRssTvEpisodeEntity:
    def test_from_orm(self):
        mock = MagicMock()
        mock.ID = 1
        mock.RSSID = "tv1"
        mock.EPISODES = "1,2,3"
        entity = RssTvEpisodeEntity.from_orm(mock)
        assert entity.episodes == "1,2,3"


class TestRssMovieRepositoryAdapter:
    def _create_mock_repo(self):
        return MagicMock()

    def test_get_all(self):
        mock_repo = self._create_mock_repo()
        mock_orm = MagicMock()
        mock_orm.ID = 1
        mock_orm.NAME = "Test"
        mock_repo.get_rss_movies.return_value = [mock_orm]

        adapter = RssMovieRepositoryAdapter(mock_repo)
        result = adapter.get_all(state="D")
        assert len(result) == 1
        assert result[0].name == "Test"

    def test_get_id(self):
        mock_repo = self._create_mock_repo()
        mock_repo.get_rss_movie_id.return_value = "123"
        adapter = RssMovieRepositoryAdapter(mock_repo)
        assert adapter.get_id("Test", "2023") == "123"

    def test_is_exists(self):
        mock_repo = self._create_mock_repo()
        mock_repo.is_exists_rss_movie.return_value = True
        adapter = RssMovieRepositoryAdapter(mock_repo)
        assert adapter.is_exists("Test", "2023") is True

    def test_delete(self):
        mock_repo = self._create_mock_repo()
        adapter = RssMovieRepositoryAdapter(mock_repo)
        adapter.delete(rssid=1)
        mock_repo.delete_rss_movie.assert_called_once_with(None, None, 1, None)

    def test_insert(self):
        mock_repo = self._create_mock_repo()
        mock_repo.insert_rss_movie.return_value = 0
        adapter = RssMovieRepositoryAdapter(mock_repo)
        media_info = MagicMock()
        media_info.title = "Test Movie"
        media_info.year = "2023"
        result = adapter.insert(media_info=media_info, state="D")
        assert result == 0
        mock_repo.insert_rss_movie.assert_called_once()

    def test_update_filter_order(self):
        mock_repo = self._create_mock_repo()
        adapter = RssMovieRepositoryAdapter(mock_repo)
        adapter.update_filter_order(1, 100)
        mock_repo.update_rss_filter_order.assert_called_once()

    def test_get_filter_order(self):
        mock_repo = self._create_mock_repo()
        mock_repo.get_rss_overedition_order.return_value = 100
        adapter = RssMovieRepositoryAdapter(mock_repo)
        result = adapter.get_filter_order(1)
        assert result == 100


class TestRssTvRepositoryAdapter:
    def _create_mock_repo(self):
        return MagicMock()

    def test_get_all(self):
        mock_repo = self._create_mock_repo()
        mock_repo.get_rss_tvs.return_value = []
        adapter = RssTvRepositoryAdapter(mock_repo)
        assert adapter.get_all() == []

    def test_update_lack(self):
        mock_repo = self._create_mock_repo()
        adapter = RssTvRepositoryAdapter(mock_repo)
        adapter.update_lack(title=None, year=None, season=None, rssid=1, lack_episodes=[1, 2, 3])
        mock_repo.update_rss_tv_lack.assert_called_once()

    def test_insert(self):
        mock_repo = self._create_mock_repo()
        mock_repo.insert_rss_tv.return_value = 0
        adapter = RssTvRepositoryAdapter(mock_repo)
        media_info = MagicMock()
        media_info.title = "Test TV"
        media_info.year = "2023"
        result = adapter.insert(media_info=media_info, total=10, lack=0, state="D")
        assert result == 0
        mock_repo.insert_rss_tv.assert_called_once()

    def test_update_filter_order(self):
        mock_repo = self._create_mock_repo()
        adapter = RssTvRepositoryAdapter(mock_repo)
        adapter.update_filter_order(1, 100)
        mock_repo.update_rss_filter_order.assert_called_once()

    def test_get_filter_order(self):
        mock_repo = self._create_mock_repo()
        mock_repo.get_rss_overedition_order.return_value = 100
        adapter = RssTvRepositoryAdapter(mock_repo)
        result = adapter.get_filter_order(1)
        assert result == 100


class TestRssTvEpisodeRepositoryAdapter:
    def _create_mock_repo(self):
        return MagicMock()

    def test_is_exists(self):
        mock_repo = self._create_mock_repo()
        mock_repo.is_exists_rss_tv_episodes.return_value = True
        adapter = RssTvEpisodeRepositoryAdapter(mock_repo)
        assert adapter.is_exists(1) is True

    def test_get(self):
        mock_repo = self._create_mock_repo()
        mock_repo.get_rss_tv_episodes.return_value = [1, 2, 3]
        adapter = RssTvEpisodeRepositoryAdapter(mock_repo)
        assert adapter.get(1) == [1, 2, 3]

    def test_delete_all(self):
        mock_repo = self._create_mock_repo()
        adapter = RssTvEpisodeRepositoryAdapter(mock_repo)
        adapter.delete_all()
        mock_repo.truncate_rss_episodes.assert_called_once()


class TestRssHistoryRepositoryAdapter:
    def _create_mock_repo(self):
        return MagicMock()

    def test_get_all(self):
        mock_repo = self._create_mock_repo()
        mock_orm = MagicMock()
        mock_orm.ID = 1
        mock_orm.NAME = "History"
        mock_repo.get_rss_history.return_value = [mock_orm]
        adapter = RssHistoryRepositoryAdapter(mock_repo)
        result = adapter.get_all(rtype="MOV")
        assert len(result) == 1

    def test_insert(self):
        mock_repo = self._create_mock_repo()
        adapter = RssHistoryRepositoryAdapter(mock_repo)
        adapter.insert("rss1", "MOV", "Test", "2023", "123", "img", "desc")
        mock_repo.insert_rss_history.assert_called_once()

    def test_check_exists(self):
        mock_repo = self._create_mock_repo()
        mock_repo.check_rss_history.return_value = False
        adapter = RssHistoryRepositoryAdapter(mock_repo)
        assert adapter.check_exists("MOV", "Test", "2023", "S01") is False

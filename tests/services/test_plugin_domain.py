"""
Plugin / TMDB黑名单领域层测试
测试 Plugin 实体 from_orm/to_dict 以及适配器代理行为
"""
from unittest.mock import MagicMock

import pytest

from app.db.repositories.plugin_repo_adapter import (
    PluginHistoryRepositoryAdapter,
    TmdbBlacklistRepositoryAdapter,
)
from app.domain.entities.plugin import PluginHistoryEntity, TmdbBlacklistEntity


def _make_orm(**kwargs):
    m = MagicMock()
    for k, v in kwargs.items():
        setattr(m, k, v)
    return m


class TestPluginHistoryEntity:
    def test_from_orm(self):
        orm = _make_orm(ID=1, PLUGIN_ID="p1", KEY="k", VALUE="v", DATE="2024-01-01")
        e = PluginHistoryEntity.from_orm(orm)
        assert e.plugin_id == "p1"
        assert e.key == "k"

    def test_from_orm_none(self):
        assert PluginHistoryEntity.from_orm(None) is None

    def test_to_dict(self):
        e = PluginHistoryEntity(id=1, plugin_id="p", key="k", value="v", date="d")
        assert e.to_dict()["plugin_id"] == "p"

    def test_getattr_uppercase(self):
        e = PluginHistoryEntity(id=1, plugin_id="p", key="k", value="v", date="d")
        assert e.PLUGIN_ID == "p"
        with pytest.raises(AttributeError):
            _ = e.NOT_EXIST


class TestTmdbBlacklistEntity:
    def test_from_orm(self):
        orm = _make_orm(
            ID=1, TMDB_ID="123", TITLE="t", YEAR="2024", MEDIA_TYPE="movie",
            POSTER_PATH="/p", BACKDROP_PATH="/b", NOTE="n",
        )
        e = TmdbBlacklistEntity.from_orm(orm)
        assert e.tmdb_id == "123"
        assert e.title == "t"
        assert e.media_type == "movie"

    def test_to_dict(self):
        e = TmdbBlacklistEntity(
            id=1, tmdb_id="123", title=None, year=None, media_type=None,
            poster_path=None, backdrop_path=None, note=None,
        )
        assert e.to_dict()["tmdb_id"] == "123"


class TestPluginHistoryRepositoryAdapter:
    def _make(self):
        hist_orm = _make_orm(ID=1, PLUGIN_ID="p", KEY="k", VALUE="v", DATE="d")
        mock = MagicMock()
        mock.insert_plugin_history = MagicMock(return_value=True)
        mock.get_plugin_history = MagicMock(return_value=[hist_orm])
        mock.update_plugin_history = MagicMock(return_value=True)
        mock.delete_plugin_history = MagicMock(return_value=True)
        return mock

    def test_get_plugin_history_list(self):
        mock = self._make()
        adapter = PluginHistoryRepositoryAdapter(repo=mock)
        results = adapter.get_plugin_history("p1")
        assert len(results) == 1
        assert results[0].plugin_id == "p"

    def test_get_plugin_history_single(self):
        mock = self._make()
        mock.get_plugin_history = MagicMock(return_value=_make_orm(ID=1, PLUGIN_ID="p", KEY="k", VALUE="v", DATE="d"))
        adapter = PluginHistoryRepositoryAdapter(repo=mock)
        results = adapter.get_plugin_history("p1", key="k")
        assert len(results) == 1

    def test_insert_update_delete(self):
        mock = self._make()
        adapter = PluginHistoryRepositoryAdapter(repo=mock)
        assert adapter.insert_plugin_history("p", "k", "v") is True
        assert adapter.update_plugin_history("p", "k", "v2") is True
        assert adapter.delete_plugin_history("p", "k") is True

    def test_default_repo(self):
        adapter = PluginHistoryRepositoryAdapter()
        assert adapter._repo is not None


class TestTmdbBlacklistRepositoryAdapter:
    def _make(self):
        bl_orm = _make_orm(
            ID=1, TMDB_ID="123", TITLE="t", YEAR="2024", MEDIA_TYPE="movie",
            POSTER_PATH="/p", BACKDROP_PATH="/b", NOTE="n",
        )
        mock = MagicMock()
        mock.is_tmdb_blacklisted = MagicMock(return_value=False)
        mock.get_tmdb_blacklist = MagicMock(return_value=[bl_orm])
        mock.insert_tmdb_blacklist = MagicMock(return_value=True)
        mock.delete_tmdb_blacklist = MagicMock(return_value=True)
        mock.clear_tmdb_blacklist = MagicMock(return_value=True)
        return mock

    def test_is_tmdb_blacklisted(self):
        mock = self._make()
        adapter = TmdbBlacklistRepositoryAdapter(repo=mock)
        assert adapter.is_tmdb_blacklisted("123") is False
        mock.is_tmdb_blacklisted.assert_called_once_with("123", None)

    def test_get_tmdb_blacklist(self):
        mock = self._make()
        adapter = TmdbBlacklistRepositoryAdapter(repo=mock)
        results = adapter.get_tmdb_blacklist()
        assert len(results) == 1
        assert results[0].tmdb_id == "123"

    def test_insert_and_delete(self):
        mock = self._make()
        adapter = TmdbBlacklistRepositoryAdapter(repo=mock)
        assert adapter.insert_tmdb_blacklist("123", title="t") is True
        assert adapter.delete_tmdb_blacklist("123") is True
        assert adapter.clear_tmdb_blacklist() is True

    def test_default_repo(self):
        adapter = TmdbBlacklistRepositoryAdapter()
        assert adapter._repo is not None

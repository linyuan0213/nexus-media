"""
自定义识别词领域层测试
测试 Word 实体 from_orm/to_dict 以及适配器代理行为
"""

from unittest.mock import MagicMock

import pytest

from app.db.repositories.word_repo_adapter import (
    CustomWordGroupRepositoryAdapter,
    CustomWordRepositoryAdapter,
)
from app.domain.entities.word import CustomWordEntity, CustomWordGroupEntity


def _make_orm(**kwargs):
    m = MagicMock()
    for k, v in kwargs.items():
        setattr(m, k, v)
    return m


class TestCustomWordEntity:
    def test_from_orm_full(self):
        orm = _make_orm(
            ID=1,
            REPLACED="a",
            REPLACE="b",
            FRONT="c",
            BACK="d",
            OFFSET="1",
            TYPE=2,
            GROUP_ID=3,
            SEASON=1,
            ENABLED=1,
            REGEX=0,
            HELP="h",
            NOTE="n",
        )
        e = CustomWordEntity.from_orm(orm)
        assert e.id == 1
        assert e.replaced == "a"
        assert e.replace == "b"
        assert e.type == 2
        assert e.enabled == 1

    def test_from_orm_none(self):
        assert CustomWordEntity.from_orm(None) is None

    def test_to_dict(self):
        e = CustomWordEntity(
            id=1,
            replaced="a",
            replace="b",
            front=None,
            back=None,
            offset=None,
            type=1,
            group_id=0,
            season=0,
            enabled=1,
            regex=0,
            help=None,
            note=None,
        )
        d = e.to_dict()
        assert d["replaced"] == "a"
        assert d["type"] == 1

    def test_getattr_uppercase_compat(self):
        e = CustomWordEntity(
            id=1,
            replaced="a",
            replace="b",
            front=None,
            back=None,
            offset=None,
            type=1,
            group_id=0,
            season=0,
            enabled=1,
            regex=0,
            help=None,
            note=None,
        )
        assert e.REPLACED == "a"
        assert e.TYPE == 1
        with pytest.raises(AttributeError):
            _ = e.NOT_EXIST


class TestCustomWordGroupEntity:
    def test_from_orm(self):
        orm = _make_orm(ID=1, TITLE="t", YEAR="2024", TYPE=1, TMDBID=123, SEASON_COUNT=2, NOTE="n")
        e = CustomWordGroupEntity.from_orm(orm)
        assert e.title == "t"
        assert e.tmdbid == 123

    def test_to_dict(self):
        e = CustomWordGroupEntity(
            id=1,
            title="t",
            year=None,
            type=0,
            tmdbid=0,
            season_count=0,
            note=None,
        )
        assert e.to_dict()["title"] == "t"


class TestCustomWordRepositoryAdapter:
    def _make(self):
        word_orm = _make_orm(
            ID=1,
            REPLACED="a",
            REPLACE="b",
            FRONT=None,
            BACK=None,
            OFFSET=None,
            TYPE=1,
            GROUP_ID=0,
            SEASON=0,
            ENABLED=1,
            REGEX=0,
            HELP=None,
            NOTE=None,
        )
        mock = MagicMock()
        mock.get_custom_words = MagicMock(return_value=[word_orm])
        mock.is_custom_words_existed = MagicMock(return_value=True)
        mock.insert_custom_word = MagicMock(return_value=True)
        mock.delete_custom_word = MagicMock(return_value=True)
        mock.check_custom_word = MagicMock(return_value=True)
        return mock

    def test_get_custom_words(self):
        mock = self._make()
        adapter = CustomWordRepositoryAdapter(repo=mock)
        results = adapter.get_custom_words(gid=1)
        assert len(results) == 1
        assert results[0].replaced == "a"
        mock.get_custom_words.assert_called_once_with(wid=None, gid=1, enabled=None)

    def test_is_custom_words_existed(self):
        mock = self._make()
        adapter = CustomWordRepositoryAdapter(repo=mock)
        assert adapter.is_custom_words_existed(replaced="x") is True
        mock.is_custom_words_existed.assert_called_once_with(replaced="x", front=None, back=None)

    def test_insert_custom_word(self):
        mock = self._make()
        adapter = CustomWordRepositoryAdapter(repo=mock)
        adapter.insert_custom_word("a", "b", "", "", "", 1, 0, 0, 1, 0, "")
        mock.insert_custom_word.assert_called_once()

    def test_default_repo(self):
        adapter = CustomWordRepositoryAdapter()
        assert adapter._repo is not None


class TestCustomWordGroupRepositoryAdapter:
    def _make(self):
        group_orm = _make_orm(ID=1, TITLE="t", YEAR="2024", TYPE=1, TMDBID=123, SEASON_COUNT=2, NOTE=None)
        mock = MagicMock()
        mock.get_custom_word_groups = MagicMock(return_value=[group_orm])
        mock.is_custom_word_group_existed = MagicMock(return_value=False)
        mock.insert_custom_word_groups = MagicMock(return_value=True)
        mock.delete_custom_word_group = MagicMock(return_value=True)
        return mock

    def test_get_custom_word_groups(self):
        mock = self._make()
        adapter = CustomWordGroupRepositoryAdapter(repo=mock)
        results = adapter.get_custom_word_groups(tmdbid=123)
        assert len(results) == 1
        assert results[0].title == "t"

    def test_is_custom_word_group_existed(self):
        mock = self._make()
        adapter = CustomWordGroupRepositoryAdapter(repo=mock)
        assert adapter.is_custom_word_group_existed(tmdbid=123, gtype=1) is False

    def test_insert_and_delete(self):
        mock = self._make()
        adapter = CustomWordGroupRepositoryAdapter(repo=mock)
        assert adapter.insert_custom_word_groups("t", "2024", 1, 123, 2) is True
        assert adapter.delete_custom_word_group(1) is True

    def test_default_repo(self):
        adapter = CustomWordGroupRepositoryAdapter()
        assert adapter._repo is not None

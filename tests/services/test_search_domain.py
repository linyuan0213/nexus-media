# -*- coding: utf-8 -*-
"""
搜索领域层测试
测试 SearchRepositoryAdapter 与 ISearchRepository 接口
"""
from unittest.mock import MagicMock

import pytest

from app.db.repositories.search_repo_adapter import SearchRepositoryAdapter


class TestSearchRepositoryAdapter:
    def _create_mock_repo(self):
        mock = MagicMock()
        mock.insert_search_results = MagicMock()
        mock.get_search_result_by_id = MagicMock(return_value="result")
        mock.get_search_results = MagicMock(return_value=["r1", "r2"])
        mock.delete_all_search_torrents = MagicMock()
        return mock

    def test_insert_search_results(self):
        mock = self._create_mock_repo()
        adapter = SearchRepositoryAdapter(repo=mock)
        adapter.insert_search_results([{"title": "Test"}], title="T", ident_flag=True)
        mock.insert_search_results.assert_called_once_with([{"title": "Test"}], "T", True)

    def test_get_search_result_by_id(self):
        mock = self._create_mock_repo()
        adapter = SearchRepositoryAdapter(repo=mock)
        result = adapter.get_search_result_by_id(1)
        assert result == "result"
        mock.get_search_result_by_id.assert_called_once_with(1)

    def test_get_search_results(self):
        mock = self._create_mock_repo()
        adapter = SearchRepositoryAdapter(repo=mock)
        results = adapter.get_search_results()
        assert results == ["r1", "r2"]
        mock.get_search_results.assert_called_once()

    def test_delete_all_search_torrents(self):
        mock = self._create_mock_repo()
        adapter = SearchRepositoryAdapter(repo=mock)
        adapter.delete_all_search_torrents()
        mock.delete_all_search_torrents.assert_called_once()

    def test_default_repo(self):
        """测试不传repo时自动创建默认实例"""
        adapter = SearchRepositoryAdapter()
        assert adapter._repo is not None

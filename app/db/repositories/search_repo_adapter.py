# -*- coding: utf-8 -*-
"""
搜索领域 Repository 适配器
将旧版 SearchRepository 适配为新领域接口
"""
from typing import Optional

from app.domain.interfaces.search_repo import ISearchRepository
from app.db.repositories.search_repository import SearchRepository


class SearchRepositoryAdapter(ISearchRepository):
    """搜索结果仓储适配器"""

    def __init__(self, repo: Optional[SearchRepository] = None):
        self._repo = repo or SearchRepository()

    def insert_search_results(self, media_items: list, title=None, ident_flag=True) -> None:
        self._repo.insert_search_results(media_items, title, ident_flag)

    def get_search_result_by_id(self, dl_id):
        return self._repo.get_search_result_by_id(dl_id)

    def get_search_results(self):
        return self._repo.get_search_results()

    def delete_all_search_torrents(self) -> None:
        self._repo.delete_all_search_torrents()

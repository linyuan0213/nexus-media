"""
搜索领域 Repository 接口（Python Protocol）
定义搜索结果仓储契约
"""

from typing import Any, Protocol


class ISearchRepository(Protocol):
    """搜索结果仓储接口"""

    def insert_search_results(self, media_items: list, title=None, ident_flag=True) -> None:
        """保存搜索结果到数据库"""
        ...

    def get_search_result_by_id(self, dl_id) -> Any:
        """根据ID获取搜索结果"""
        ...

    def get_search_results(self) -> list[Any]:
        """获取所有搜索结果"""
        ...

    def delete_all_search_torrents(self) -> None:
        """删除所有搜索结果"""
        ...

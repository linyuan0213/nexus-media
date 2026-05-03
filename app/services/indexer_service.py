# -*- coding: utf-8 -*-
"""
IndexerService - 索引器业务服务层
将 app/indexer/ 中散落的业务逻辑收口为可独立测试的 Service。
职责：
- 索引器站点查询与管理
- 搜索委托给 SearchService/Searcher（避免重复）
- 资源列表获取
- 索引器统计
"""
from typing import Any, Dict, List, Optional, Tuple

from app.indexer import Indexer
from app.indexer.client import BuiltinIndexer
from app.db.repositories.download_repo_adapter import IndexerStatisticsRepositoryAdapter
from app.domain.interfaces.download_repo import IIndexerStatisticsRepository
from app.schemas.download import IndexerStatisticsDTO
from app.schemas.indexer import (
    IndexerClientInfoDTO,
    IndexerHashDTO,
    IndexerResourcesResultDTO,
    UserIndexerDTO,
)
from app.utils import StringUtils


class IndexerService:
    """
    索引器业务服务
    不直接操作 HTTP 请求，接收/返回显式 DTO，依赖通过构造函数注入。
    """

    def __init__(self,
                 indexer: Optional[Indexer] = None,
                 string_utils=None,
                 indexer_statistics_repo: Optional[IIndexerStatisticsRepository] = None):
        self._indexer = indexer or Indexer()
        self._string_utils = string_utils or StringUtils
        # 如果没有注入Repository，使用适配器创建默认实例
        if indexer_statistics_repo is None:
            self._indexer_statistics_repo = IndexerStatisticsRepositoryAdapter()
        else:
            self._indexer_statistics_repo = indexer_statistics_repo

    # ------------------------------------------------------------------
    # 站点管理
    # ------------------------------------------------------------------

    def get_user_indexers(self) -> List[UserIndexerDTO]:
        """
        获取用户已经选择的索引器列表
        """
        return [
            UserIndexerDTO(id=index.id, name=index.name)
            for index in self._indexer.get_indexers(check=True)
        ]

    def get_indexer_hash_dict(self) -> Dict[str, IndexerHashDTO]:
        """
        获取全部索引器的 Hash 字典（用于前端快速查找）
        """
        result: Dict[str, IndexerHashDTO] = {}
        for item in self._indexer.get_indexers() or []:
            key = self._string_utils.md5_hash(item.name)
            result[key] = IndexerHashDTO(
                id=item.id,
                name=item.name,
                public=item.public,
                builtin=item.builtin
            )
        return result

    def get_user_indexer_names(self) -> List[str]:
        """
        获取当前用户选中的索引器站点名称列表
        """
        return [indexer.name for indexer in self._indexer.get_indexers(check=True)]

    # ------------------------------------------------------------------
    # 内置索引器（兼容旧调用）
    # ------------------------------------------------------------------

    @staticmethod
    def get_builtin_indexers(check: bool = True,
                             indexer_id: Optional[str] = None) -> Any:
        """
        获取内置索引器的索引站点
        :param check: 是否过滤用户选中
        :param indexer_id: 指定站点ID
        """
        return BuiltinIndexer().get_indexers(check=check, indexer_id=indexer_id)

    # ------------------------------------------------------------------
    # 资源列表
    # ------------------------------------------------------------------

    def list_resources(self, index_id: str,
                       page: int = 0,
                       keyword: Optional[str] = None) -> IndexerResourcesResultDTO:
        """
        获取内置索引器的资源列表
        :param index_id: 内置站点ID
        :param page: 页码
        :param keyword: 搜索关键字
        """
        if not index_id:
            return IndexerResourcesResultDTO(success=True, data=[])
        resources = self._indexer.list_resources(
            index_id=index_id, page=page, keyword=keyword)
        if resources is None:
            return IndexerResourcesResultDTO(
                success=False,
                msg="获取站点资源出现错误，无法连接到站点！")
        return IndexerResourcesResultDTO(success=True, data=resources)

    # ------------------------------------------------------------------
    # 客户端信息
    # ------------------------------------------------------------------

    def get_client_info(self) -> IndexerClientInfoDTO:
        """
        获取当前索引器客户端信息
        """
        client = self._indexer.get_client()
        client_type = self._indexer.get_client_type()
        return IndexerClientInfoDTO(
            client_id=getattr(client, 'client_id', '') if client else '',
            client_type=getattr(client_type, 'value', '') if client_type else '',
            client_name=getattr(client, 'client_name', '') if client else ''
        )

    def get_client(self) -> Any:
        """
        获取当前索引器客户端实例（低层兼容）
        """
        return self._indexer.get_client()

    def get_client_type(self) -> Any:
        """
        获取当前索引器类型（低层兼容）
        """
        return self._indexer.get_client_type()

    def search_by_keyword(self, key_word, filter_args, match_media=None, in_from=None):
        """
        根据关键字搜索（代理到底层 Indexer）
        """
        return self._indexer.search_by_keyword(
            key_word=key_word,
            filter_args=filter_args,
            match_media=match_media,
            in_from=in_from
        )

    def get_indexers(self, check: bool = False):
        """
        获取索引器列表（低层兼容）
        """
        return self._indexer.get_indexers(check=check)

    def init_config(self) -> None:
        """
        刷新底层 Indexer 单例配置（兼容 IndexerConfigService）
        """
        self._indexer.init_config()

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------

    def get_indexer_statistics(self) -> Tuple[List[IndexerStatisticsDTO], List[list]]:
        """
        获取索引器统计数据及图表 dataset
        :return: (统计数据列表, 图表数据集)
        """
        client = self._indexer.get_client()
        client_id = getattr(client, 'client_id', '') if client else ''
        if not client_id:
            return [], [["indexer", "avg"]]
        result = self._indexer_statistics_repo.get_by_client(client_id)
        dataset = [["indexer", "avg"]]
        stats: List[IndexerStatisticsDTO] = []
        for entity in result:
            stats.append(IndexerStatisticsDTO(
                name=entity.indexer,
                total=entity.total,
                fail=entity.fail,
                success=entity.success,
                avg=round(entity.avg_seconds, 1)
            ))
            dataset.append([entity.indexer, str(round(entity.avg_seconds, 1))])
        return stats, dataset

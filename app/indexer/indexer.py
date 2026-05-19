"""
索引器管理模块

职责：
1. 管理所有索引器客户端（Builtin、Prowlarr、Jackett）
2. 并发调度多站点搜索
3. 收集所有原始结果后，统一调用 SearchPipeline 进行批量识别和过滤
"""

import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import log
from app.db.repositories import DownloadRepository
from app.helper import ProgressHelper
from app.indexer.core import SearchPipeline
from app.indexer.registry import get_all_clients, get_client_class
from app.utils import ExceptionUtils, StringUtils
from app.utils.commons import SingletonMeta
from app.utils.types import ProgressKey, SearchType


class Indexer(metaclass=SingletonMeta):
    """
    索引器管理单例

    搜索流程：
    1. 获取所有可用站点
    2. 并发搜索每个站点，收集原始结果（dict 列表）
    3. 将所有原始结果传入 SearchPipeline，统一批量识别和过滤
    4. 返回最终结果（meta_info 列表）
    """

    def __init__(self):
        self.init_config()

    def init_config(self):
        self.progress = ProgressHelper()
        self.download_repo = DownloadRepository()
        from app.core.system_config import SystemConfig
        from app.utils.types import SystemConfigKey

        indexer = SystemConfig().get(SystemConfigKey.SearchIndexer) or "builtin"
        self._client = self.__get_client(indexer)
        if self._client:
            self._client_type = self._client.get_type()
        else:
            self._client_type = None
        self._pipeline = SearchPipeline()

    def __build_class(self, ctype, conf):
        for cls in get_all_clients():
            try:
                if cls.match(ctype):
                    return cls(conf)
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
        return None

    def __get_client(self, ctype, conf=None):
        return self.__build_class(ctype=ctype, conf=conf)

    def get_client(self):
        return self._client

    def get_client_type(self):
        return self._client_type

    def get_indexers(self, check=False):
        if not self._client:
            return []
        return self._client.get_indexers(check=check)

    def get_user_indexer_dict(self):
        return [{"id": index.id, "name": index.name} for index in self.get_indexers(check=True)]

    def get_indexer_hash_dict(self):
        indexer_dict = {}
        for item in self.get_indexers() or []:
            indexer_dict[StringUtils.md5_hash(item.name)] = {
                "id": item.id,
                "name": item.name,
                "public": item.public,
                "builtin": item.builtin,
            }
        return indexer_dict

    def get_user_indexer_names(self):
        return [indexer.name for indexer in self.get_indexers(check=True)]

    @staticmethod
    def get_builtin_indexers(check=True, indexer_id=None):
        cls = get_client_class("builtin")
        if cls:
            return cls().get_indexers(check=check, indexer_id=indexer_id)
        return []

    def list_resources(self, index_id, page=0, keyword=None):
        cls = get_client_class("builtin")
        if cls:
            return cls().list(index_id=index_id, page=page, keyword=keyword)
        return []

    def search_by_keyword(self, key_word, filter_args: dict, match_media=None, in_from: SearchType | None = None):
        """
        根据关键字调用索引器搜索

        :param key_word: 搜索关键词
        :param filter_args: 过滤条件
        :param match_media: 需要匹配的媒体信息
        :param in_from: 搜索渠道
        :return: 命中的资源媒体信息列表
        """
        if not key_word:
            return []

        progress_key = ProgressKey.RssSearch if in_from == SearchType.RSS else ProgressKey.Search
        if not self._client:
            return []

        _client = self._client
        _client_type = self._client_type
        indexers = self.get_indexers(check=True)
        if not indexers:
            log.error("没有配置索引器，无法搜索！")
            return []

        start_time = datetime.datetime.now()
        max_workers = min(len(indexers), 15)

        if filter_args and filter_args.get("site"):
            log.info(
                f"【{_client_type.value if _client_type else ''}】开始搜索 %s，站点：%s，并发数：%s ..."
                % (key_word, filter_args.get("site"), max_workers)
            )
            self.progress.update(
                ptype=progress_key, text="开始搜索 {}，站点：{} ...".format(key_word, filter_args.get("site"))
            )
        else:
            log.info(
                f"【{_client_type.value if _client_type else ''}】开始并行搜索 %s，站点数：%s，并发数：%s ..."
                % (key_word, len(indexers), max_workers)
            )
            self.progress.update(ptype=progress_key, text=f"开始并行搜索 {key_word}，站点数：{len(indexers)} ...")

        # ---------- 阶段1：并发搜索所有站点，收集原始结果 ----------
        all_raw_results = []
        executor = ThreadPoolExecutor(max_workers=max_workers)
        try:
            all_task = []
            for index in indexers:
                order_seq = 100 - int(index.pri)
                task = executor.submit(
                    _client.search, order_seq, index, key_word, filter_args, match_media, in_from
                )
                all_task.append(task)

            for future in as_completed(all_task):
                result = future.result()
                if result:
                    all_raw_results.extend(result)
        finally:
            executor.shutdown(wait=False)

        # ---------- 阶段2：统一批量识别和过滤 ----------
        pipeline_result = self._pipeline.process(
            all_results=all_raw_results,
            filter_args=filter_args,
            match_media=match_media,
            in_from=in_from,
            progress_key=progress_key,
        )

        end_time = datetime.datetime.now()
        log.info(
                f"【{_client_type.value if _client_type else ''}】搜索关键词 {key_word} 所有站点完成，"
            f"原始结果 {len(all_raw_results)} 条，有效资源数：{len(pipeline_result.results)}，"
            f"总耗时 {(end_time - start_time).seconds} 秒"
        )
        self.progress.update(
            ptype=progress_key,
            text=f"搜索关键词 {key_word} 所有站点完成，有效资源数：{len(pipeline_result.results)}，总耗时 {(end_time - start_time).seconds} 秒",
        )

        return pipeline_result.results

    def get_indexer_statistics(self):
        """获取索引器统计信息"""
        if not self._client:
            return {}
        return self.download_repo.get_indexer_statistics(self._client.get_client_id())

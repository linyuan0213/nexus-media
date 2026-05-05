# -*- coding: utf-8 -*-
"""
SearchService - 搜索业务层

按 Clean Architecture 拆分为：
- SearchQueryBuilder：搜索词构建
- SearchExecutor：并发搜索执行（统一线程池生命周期）
- SearchResultDeduplicator：搜索结果去重
- SearchResultProcessor：结果过滤、排序、入库、择优下载
- Searcher：对外保留的入口类（兼容旧调用）
- SearchService：Service 层包装
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, List, Optional, Tuple

import log
from app.db.repositories.search_repo_adapter import SearchRepositoryAdapter
from app.db.repositories.download_repo_adapter import DownloadHistoryRepositoryAdapter
from app.domain.interfaces.download_repo import IDownloadHistoryRepository
from app.domain.interfaces.search_repo import ISearchRepository
from app.services.downloader_core import DownloaderCore as Downloader
from app.services.indexer_service import IndexerService
from app.media import Media
from app.message import Message
from app.plugin_framework.event_compat import EventManager
from app.helper import ProgressHelper
from app.schemas.search import SearchOneMediaResultDTO, SearchMediasResultDTO
from app.utils.commons import SingletonMeta
from app.utils.string_utils import StringUtils
from app.utils.types import SearchType, EventType, ProgressKey
from config import Config


class SearchQueryBuilder:
    """
    搜索查询构建器
    职责：根据媒体信息构建多语言搜索词列表
    """

    @staticmethod
    def build_search_names(media_info, media_helper: Optional[Media] = None) -> Tuple[List[str], int]:
        """
        根据媒体信息构建多语言搜索词列表
        :return: (搜索词列表, 建议最大并发数)
        """
        search_name_list = []
        if media_info.keyword:
            search_name_list.append(media_info.keyword)
            return list(filter(None, search_name_list)), 1

        # 中文名
        if media_info.cn_name:
            search_cn_name = media_info.cn_name
        else:
            search_cn_name = media_info.title

        # 英文名
        search_en_name = None
        if media_info.en_name:
            search_en_name = media_info.en_name
        else:
            if media_info.original_language == "en":
                search_en_name = media_info.original_title
            else:
                _media = media_helper or Media()
                en_title = _media.get_tmdb_en_title(media_info)
                if en_title:
                    search_en_name = en_title

        search_name_list.append(search_cn_name)
        search_name_list.append(search_en_name)

        # 开启多语言搜索
        max_workers = 1
        try:
            multi_lang = Config().get_config("laboratory").get("search_multi_language")
        except Exception:
            multi_lang = False
        if multi_lang:
            _media = media_helper or Media()
            search_zhtw_name = _media.get_tmdb_zhtw_title(media_info)
            if search_zhtw_name and search_zhtw_name != search_cn_name:
                search_name_list.append(search_zhtw_name)
            if media_info.original_language != 'cn' and search_en_name != media_info.original_title:
                search_name_list.append(media_info.original_title)
            max_workers = len(search_name_list)

        return list(filter(None, search_name_list)), max_workers


class SearchExecutor:
    """
    搜索执行器
    职责：统一管理搜索线程池生命周期，执行并发搜索
    """

    def __init__(self, max_workers: int = 8, thread_name_prefix: str = "search"):
        self._max_workers = max_workers
        self._thread_name_prefix = thread_name_prefix

    def execute(self, search_func, search_names: list, filter_args: dict,
                media_info, in_from: SearchType,
                progress_updater=None) -> List[Any]:
        """
        并发执行多词搜索
        :param search_func: 单次搜索函数（如 Searcher.search_medias）
        :param progress_updater: 可选的进度更新回调 (finish_count, total)
        :return: 合并后的搜索结果列表
        """
        if not search_names:
            return []

        optimal_workers = min(len(search_names), self._max_workers)
        media_list = []
        all_task = []

        with ThreadPoolExecutor(max_workers=optimal_workers,
                                thread_name_prefix=self._thread_name_prefix) as executor:
            for search_name in search_names:
                task = executor.submit(search_func,
                                       search_name,
                                       filter_args,
                                       media_info,
                                       in_from)
                all_task.append(task)

            finish_count = 0
            total = len(all_task)
            for future in as_completed(all_task):
                result = future.result()
                finish_count += 1
                if progress_updater:
                    progress_updater(finish_count, total)
                if result:
                    media_list.extend(result)

        return media_list


class SearchResultDeduplicator:
    """
    搜索结果去重器
    职责：基于 org_string + site + description 对搜索结果去重
    """

    @staticmethod
    def deduplicate(media_list: list) -> list:
        """对搜索结果列表进行去重"""
        if not media_list:
            return []
        unique_media_list = []
        media_seen = set()
        for d in media_list:
            org_string = StringUtils.md5_hash(
                f'{d.org_string}{d.site}{d.description or ""}')
            if org_string not in media_seen:
                unique_media_list.append(d)
                media_seen.add(org_string)
        return unique_media_list


class SearchResultProcessor:
    """
    搜索结果处理器
    职责：排序、入库、过滤已下载、择优下载
    """

    def __init__(self,
                 downloader: Optional[Downloader] = None,
                 download_repo: Optional[IDownloadHistoryRepository] = None,
                 search_repo: Optional[ISearchRepository] = None,
                 message: Optional[Message] = None):
        self._downloader = downloader or Downloader()
        # 如果没有注入Repository，使用适配器创建默认实例
        if download_repo is None:
            self._download_repo = DownloadHistoryRepositoryAdapter()
        else:
            self._download_repo = download_repo
        self._search_repo = search_repo or SearchRepositoryAdapter()
        self._message = message or Message()

    @staticmethod
    def sort_results(media_list: list) -> list:
        """按标题、资源顺序、站点顺序、做种数排序"""
        return sorted(media_list, key=lambda x: "%s%s%s%s" % (
            str(x.title).ljust(100, ' '),
            str(x.res_order).rjust(3, '0'),
            str(x.site_order).rjust(3, '0'),
            str(x.seeders).rjust(10, '0')
        ), reverse=True)

    def filter_downloaded(self, media_list: list) -> list:
        """过滤掉已在下载历史中存在的资源"""
        filtered = []
        for media_item in media_list:
            if media_item.tmdb_id:
                season_episode = media_item.get_season_episode_string()
                if self._download_repo.is_exists_by_tmdb(
                        media_item.tmdb_id, season_episode):
                    log.info(f"【Searcher】{media_item.title} {season_episode} 已在下载历史中存在，跳过下载")
                    continue
            filtered.append(media_item)
        return filtered

    def persist_results(self, media_list: list, title=None, ident_flag=True) -> None:
        """清空并保存搜索结果到数据库"""
        self._search_repo.delete_all_search_torrents()
        self._search_repo.insert_search_results(media_list, title, ident_flag)

    def batch_download(self, media_list: list, in_from: SearchType,
                       no_exists: dict, user_name=None):
        """择优下载"""
        return self._downloader.batch_download(
            in_from=in_from,
            media_list=media_list,
            need_tvs=no_exists,
            user_name=user_name
        )


class Searcher(metaclass=SingletonMeta):
    """
    搜索器（兼容原 app/searcher.py 的入口类）
    内部已拆分为 SearchQueryBuilder / SearchExecutor / SearchResultDeduplicator / SearchResultProcessor
    """
    downloader = None
    media = None
    message = None
    indexer = None
    progress = None
    search_repo = None
    eventmanager = None

    _search_auto = True

    def __init__(self,
                 download_repo: Optional[IDownloadHistoryRepository] = None,
                 search_repo: Optional[ISearchRepository] = None):
        self._download_repo = download_repo
        self._search_repo = search_repo
        self.init_config()

    def init_config(self):
        self.downloader = Downloader()
        self.media = Media()
        self.message = Message()
        self.progress = ProgressHelper()
        # 如果没有注入Repository，使用适配器创建默认实例
        if self._download_repo is None:
            self._download_repo = DownloadHistoryRepositoryAdapter()
        if self._search_repo is None:
            self._search_repo = SearchRepositoryAdapter()
        self.search_repo = self._search_repo
        self.indexer_service = IndexerService()
        self.eventmanager = EventManager()
        self._search_auto = Config().get_config("pt").get('search_auto', True)

    @property
    def download_repo(self):
        """兼容旧代码访问 download_repo 属性"""
        return self._download_repo

    def search_medias(self,
                      key_word,
                      filter_args: dict,
                      match_media=None,
                      in_from: SearchType = None):
        """
        根据关键字调用索引器检查媒体
        """
        if not key_word:
            return []
        if not self.indexer_service:
            return []
        self.eventmanager.send_event(EventType.SearchStart, {
            "key_word": key_word,
            "media_info": match_media.to_dict() if match_media else None,
            "filter_args": filter_args,
            "search_type": in_from.value if in_from else None
        })
        return self.indexer_service.search_by_keyword(key_word=key_word,
                                                      filter_args=filter_args,
                                                      match_media=match_media,
                                                      in_from=in_from)

    def search_one_media(self, media_info,
                         in_from: SearchType,
                         no_exists: dict,
                         sites: list = None,
                         filters: dict = None,
                         user_name=None):
        """
        只搜索和下载一个资源
        """
        if not media_info:
            return None, {}, 0, 0

        self.progress.start(
            ProgressKey.RssSearch if in_from == SearchType.RSS else ProgressKey.Search)

        # 季/集信息
        search_season = None if media_info.begin_season is None else media_info.get_season_list()
        search_episode = media_info.get_episode_list()
        if search_episode and not search_season:
            search_season = [1]

        filter_args = {
            "season": search_season,
            "episode": search_episode,
            "year": media_info.year,
            "type": media_info.type,
            "site": sites,
            "seeders": True
        }
        if filters:
            filter_args.update(filters)

        # 1. 构建搜索词
        search_name_list, max_workers = SearchQueryBuilder.build_search_names(
            media_info, self.media)

        if media_info.keyword:
            media_list = self.search_medias(
                media_info.keyword, filter_args, media_info, in_from)
        else:
            log.info("【Searcher】开始搜索 %s ..." % search_name_list)
            optimal_workers = min(len(search_name_list), max_workers, 8)

            # 2. 并发执行搜索
            executor = SearchExecutor(max_workers=optimal_workers)

            def _update_progress(finish_count, total):
                self.progress.update(
                    ptype=ProgressKey.RssSearch if in_from == SearchType.RSS else ProgressKey.Search,
                    value=round(100 * (finish_count / total)))

            media_list = executor.execute(
                search_func=self.search_medias,
                search_names=search_name_list,
                filter_args=filter_args,
                media_info=media_info,
                in_from=in_from,
                progress_updater=_update_progress
            )

        # 3. 去重
        media_list = SearchResultDeduplicator.deduplicate(media_list)

        if len(media_list) == 0:
            log.info("【Searcher】%s 未搜索到任何资源" % search_name_list)
            return None, no_exists, 0, 0

        processor = SearchResultProcessor(
            downloader=self.downloader,
            download_repo=self._download_repo,
            search_repo=self.search_repo,
            message=self.message
        )

        if in_from in self.message.get_search_types():
            # 排序并入库
            media_list = processor.sort_results(media_list)
            processor.persist_results(media_list)
            if not self._search_auto:
                return None, no_exists, len(media_list), None

        # 4. 过滤已下载
        filtered_media_list = processor.filter_downloaded(media_list)
        if not filtered_media_list:
            log.info("【Searcher】所有搜索结果已在下载历史中存在，跳过下载")
            return None, no_exists, len(media_list), 0

        # 5. 择优下载
        download_items, left_medias = processor.batch_download(
            filtered_media_list, in_from, no_exists, user_name)

        if not download_items:
            log.info("【Searcher】%s 未下载到资源" % media_info.title)
            return None, left_medias, len(media_list), 0
        else:
            log.info("【Searcher】实际下载了 %s 个资源" % len(download_items))
            if left_medias:
                return None, left_medias, len(media_list), len(download_items)
            return download_items[0], no_exists, len(media_list), len(download_items)

    def get_search_result_by_id(self, dl_id):
        return self.search_repo.get_search_result_by_id(dl_id)

    def get_search_results(self):
        return self.search_repo.get_search_results()

    def delete_all_search_torrents(self):
        self.search_repo.delete_all_search_torrents()

    def insert_search_results(self, media_items: list, title=None, ident_flag=True):
        self.search_repo.insert_search_results(media_items, title, ident_flag)


class SearchService:
    """
    搜索业务服务（Service 层包装）
    """

    def __init__(self,
                 searcher: Optional[Searcher] = None,
                 downloader: Optional[Downloader] = None,
                 media: Optional[Media] = None):
        self._searcher = searcher or Searcher()
        self._downloader = downloader or Downloader()
        self._media = media or Media()

    def search_medias(self,
                      key_word: Any,
                      filter_args: dict,
                      match_media=None,
                      in_from: Optional[SearchType] = None) -> SearchMediasResultDTO:
        if not key_word:
            return SearchMediasResultDTO(results=[])
        results = self._searcher.search_medias(
            key_word=key_word,
            filter_args=filter_args,
            match_media=match_media,
            in_from=in_from or SearchType.WEB
        )
        return SearchMediasResultDTO(results=results or [])

    def search_one_media(self,
                         media_info,
                         in_from: SearchType,
                         no_exists: dict,
                         sites: Optional[list] = None,
                         filters: Optional[dict] = None,
                         user_name: Optional[str] = None) -> SearchOneMediaResultDTO:
        result = self._searcher.search_one_media(
            media_info=media_info,
            in_from=in_from,
            no_exists=no_exists,
            sites=sites or [],
            filters=filters or {},
            user_name=user_name
        )
        if not result:
            return SearchOneMediaResultDTO()
        download_item, left_medias, total_count, download_count = result
        return SearchOneMediaResultDTO(
            media_info=download_item,
            no_exists=left_medias,
            total_count=total_count or 0,
            download_count=download_count or 0
        )

    def get_search_result_by_id(self, dl_id) -> Any:
        return self._searcher.get_search_result_by_id(dl_id)

    def get_search_results(self) -> Any:
        return self._searcher.get_search_results()

    def delete_all_search_torrents(self) -> None:
        self._searcher.delete_all_search_torrents()

    def insert_search_results(self, media_items: list, title=None, ident_flag=True) -> None:
        self._searcher.insert_search_results(media_items, title, ident_flag)

    def build_search_names(self, media_info) -> List[str]:
        names, _ = SearchQueryBuilder.build_search_names(media_info, self._media)
        return names

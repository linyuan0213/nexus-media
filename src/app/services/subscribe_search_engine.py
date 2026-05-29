"""
SubscribeSearchEngine - 订阅搜索/下载逻辑
"""

import traceback
from threading import Lock
from typing import Any

import log
from app.db.repositories import RssRepository
from app.db.repositories.rss_repo_adapter import (
    RssMovieRepositoryAdapter,
    RssTvEpisodeRepositoryAdapter,
    RssTvRepositoryAdapter,
)
from app.di import container
from app.domain.interfaces.rss_repo import (
    IRssMovieRepository,
    IRssTvEpisodeRepository,
    IRssTvRepository,
)
from app.infrastructure.distributed_lock.lock_manager import get_lock_manager
from app.media import MediaCache, MediaService, meta_info
from app.message import Message
from app.plugin_framework.event_compat import EventHandler, EventManager
from app.services.downloader_core import DownloaderCore as Downloader
from app.services.filter_service import FilterService as Filter
from app.services.search_service import Searcher
from app.utils import Torrent
from app.utils.types import MediaType, SearchType


class SubscribeSearchEngine:
    """
    订阅搜索/下载逻辑
    """

    _movie_repo: IRssMovieRepository
    _tv_repo: IRssTvRepository
    _tv_episode_repo: IRssTvEpisodeRepository

    def __init__(
        self,
        service: Any | None = None,
        rss_repo: RssRepository | None = None,
        movie_repo: IRssMovieRepository | None = None,
        tv_repo: IRssTvRepository | None = None,
        tv_episode_repo: IRssTvEpisodeRepository | None = None,
        searcher: Searcher | None = None,
        media_service: MediaService | None = None,
        media_cache: MediaCache | None = None,
        downloader: Downloader | None = None,
        filter_service: Filter | None = None,
        message: Message | None = None,
        eventmanager: EventManager | None = None,
    ):
        self._service = service
        self._rss_repo = rss_repo or RssRepository()
        # 如果没有注入领域仓库，使用适配器包装旧仓库
        if movie_repo is None:
            movie_repo = RssMovieRepositoryAdapter(self._rss_repo)
        if tv_repo is None:
            tv_repo = RssTvRepositoryAdapter(self._rss_repo)
        if tv_episode_repo is None:
            tv_episode_repo = RssTvEpisodeRepositoryAdapter(self._rss_repo)
        self._movie_repo = movie_repo
        self._tv_repo = tv_repo
        self._tv_episode_repo = tv_episode_repo
        self._searcher = searcher or container.searcher()
        self._media_service = media_service or container.media_service()
        self._media_cache = media_cache or container.media_cache()
        self._downloader = downloader or container.downloader_core()
        self._filter = filter_service or container.filter_service()
        self._message = message or container.message()
        self._eventmanager = eventmanager or EventHandler
        self._lock = Lock()

    def subscribe_search_all(self):
        """
        搜索R状态的所有订阅，由定时服务调用
        """
        self.subscribe_search(state="R")

    def subscribe_search(self, state="D"):
        """
        RSS订阅队列中状态的任务处理，先进行存量资源搜索，缺失的才标志为RSS状态，由定时服务调用
        """
        lock_key = f"subscribe:search:{state}"
        dist_lock = get_lock_manager().create_lock(lock_key, ttl_seconds=1800)
        acquired = dist_lock.acquire()
        if not acquired:
            log.info(f"[Subscribe]订阅搜索(state={state}) 正在执行，跳过")
            return
        try:
            self._lock.acquire()
            # 处理电影
            self.subscribe_search_movie(state=state)
            # 处理电视剧
            self.subscribe_search_tv(state=state)
        finally:
            self._lock.release()
            dist_lock.release()

    def subscribe_search_movie(self, rssid=None, state="D"):
        """
        搜索电影RSS
        :param rssid: 订阅ID，未输入时搜索所有状态为D的，输入时搜索该ID任何状态的
        :param state: 搜索的状态，默认为队列中才搜索
        """
        if rssid:
            rss_movies = self._service.get_subscribe_movies(rid=rssid) if self._service else {}
        else:
            rss_movies = self._service.get_subscribe_movies(state=state) if self._service else {}
        if rss_movies:
            log.info(f"[Subscribe]共有 {len(rss_movies)} 个电影订阅需要搜索")
        for _rid, rss_info in rss_movies.items():
            # 跳过模糊匹配的
            if rss_info.get("fuzzy_match"):
                continue
            # 搜索站点范围
            rssid = rss_info.get("id")
            name = rss_info.get("name")
            year = rss_info.get("year") or ""
            tmdbid = rss_info.get("tmdbid")
            over_edition = rss_info.get("over_edition")
            keyword = rss_info.get("keyword")

            # 开始搜索
            self._movie_repo.update_state(title=None, year=None, rssid=rssid, state="S")

            try:
                # 识别
                media_info = self.__get_media_info(tmdbid, name, year, MediaType.MOVIE)
                # 未识别到媒体信息
                if not media_info or not media_info.tmdb_info:
                    self._movie_repo.update_state(title=None, year=None, rssid=rssid, state="R")
                    continue
                media_info.set_download_info(
                    download_setting=rss_info.get("download_setting"), save_path=rss_info.get("save_path")
                )
                # 自定义搜索词
                media_info.keyword = keyword
                # 非洗版的情况检查是否存在
                if not over_edition:
                    # 检查是否存在
                    exist_flag, no_exists, _ = self._downloader.check_exists_medias(meta_info=media_info)
                    # 已经存在
                    if exist_flag:
                        log.info(f"[Subscribe]电影 {media_info.get_title_string()} 已存在")
                        if self._service:
                            self._service.finish_rss_subscribe(rssid=rssid, media=media_info)
                        continue
                else:
                    # 洗版时按缺失来下载
                    no_exists = {}
                    # 把洗版标志加入搜索
                    media_info.over_edition = over_edition
                    # 将当前的优先级传入搜索
                    media_info.res_order = self._movie_repo.get_filter_order(rssid=rssid)
                # 开始搜索
                filter_dict = {
                    "restype": rss_info.get("filter_restype"),
                    "pix": rss_info.get("filter_pix"),
                    "team": rss_info.get("filter_team"),
                    "rule": rss_info.get("filter_rule"),
                    "include": rss_info.get("filter_include"),
                    "exclude": rss_info.get("filter_exclude"),
                    "site": rss_info.get("search_sites"),
                }
                search_result, _, _, _ = self._searcher.search_one_media(
                    media_info=media_info,
                    in_from=SearchType.RSS,
                    no_exists=no_exists,
                    sites=rss_info.get("search_sites"),
                    filters=filter_dict,
                )
                if search_result:
                    # 洗版
                    if over_edition:
                        if self._service:
                            self._service.update_subscribe_over_edition(
                                rtype=search_result.type, rssid=rssid, media=search_result
                            )
                    else:
                        if self._service:
                            self._service.finish_rss_subscribe(rssid=rssid, media=media_info)
                else:
                    self._movie_repo.update_state(title=None, year=None, rssid=rssid, state="R")
            except Exception as err:
                self._movie_repo.update_state(title=None, year=None, rssid=rssid, state="R")
                log.error(f"[Subscribe]电影 {name} 订阅搜索失败：{str(err)}")
                log.debug(f"异常详细信息: {traceback.format_exc()}")
                continue

    def subscribe_search_tv(self, rssid=None, state="D"):
        """
        搜索电视剧RSS
        :param rssid: 订阅ID，未输入时搜索所有状态为D的，输入时检索该ID任何状态的
        :param state: 检索的状态，默认为队列中才检索
        """
        if rssid:
            rss_tvs = self._service.get_subscribe_tvs(rid=rssid) if self._service else {}
        else:
            rss_tvs = self._service.get_subscribe_tvs(state=state) if self._service else {}
        if rss_tvs:
            log.info(f"[Subscribe]共有 {len(rss_tvs)} 个电视剧订阅需要检索")
        rss_no_exists = {}
        for _rid, rss_info in rss_tvs.items():
            # 跳过模糊匹配的
            if rss_info.get("fuzzy_match"):
                continue
            rssid = rss_info.get("id")
            name = rss_info.get("name")
            year = rss_info.get("year") or ""
            tmdbid = rss_info.get("tmdbid")
            over_edition = rss_info.get("over_edition")
            keyword = rss_info.get("keyword")

            # 开始搜索
            self._tv_repo.update_state(title=None, year=None, season=None, rssid=rssid, state="S")

            try:
                # 识别
                media_info = self.__get_media_info(tmdbid, name, year, MediaType.TV)
                # 未识别到媒体信息
                if not media_info or not media_info.tmdb_info:
                    self._tv_repo.update_state(title=None, year=None, season=None, rssid=rssid, state="R")
                    continue
                # 取下载设置
                media_info.set_download_info(
                    download_setting=rss_info.get("download_setting"), save_path=rss_info.get("save_path")
                )
                # 从登记薄中获取缺失剧集
                season = 1
                if rss_info.get("season"):
                    season = int(str(rss_info.get("season")).replace("S", ""))
                # 订阅季
                media_info.begin_season = season
                # 订阅ID
                media_info.rssid = rssid
                # 自定义集数
                total_ep = rss_info.get("total")
                current_ep = rss_info.get("current_ep")
                # 自定义搜索词
                media_info.keyword = keyword
                # 表中记录的剩余订阅集数
                episodes = self._tv_episode_repo.get(rss_info.get("id"))
                if episodes is None:
                    episodes = []
                    if current_ep:
                        episodes = list(range(current_ep, total_ep + 1))
                    rss_no_exists[media_info.tmdb_id] = [
                        {"season": season, "episodes": episodes, "total_episodes": total_ep}
                    ]
                else:
                    rss_no_exists[media_info.tmdb_id] = [
                        {"season": season, "episodes": episodes, "total_episodes": total_ep}
                    ]
                # 非洗版时检查本地媒体库情况
                if not over_edition:
                    exist_flag, library_no_exists, _ = self._downloader.check_exists_medias(
                        meta_info=media_info, total_ep={season: total_ep}
                    )
                    # 当前剧集已存在，跳过
                    if exist_flag:
                        # 已全部存在
                        if not library_no_exists or not library_no_exists.get(media_info.tmdb_id):
                            log.info(f"[Subscribe]电视剧 {media_info.get_title_string()} 订阅剧集已全部存在")
                            # 完成订阅
                            if self._service:
                                self._service.finish_rss_subscribe(rssid=rss_info.get("id"), media=media_info)
                        continue
                    # 取交集做为缺失集
                    rss_no_exists = Torrent.get_intersection_episodes(
                        target=rss_no_exists, source=library_no_exists, title=media_info.tmdb_id
                    )
                    if rss_no_exists.get(media_info.tmdb_id):
                        log.info(
                            f"[Subscribe]{media_info.get_title_string()} 订阅缺失季集：{rss_no_exists.get(media_info.tmdb_id)}"
                        )
                else:
                    # 把洗版标志加入检索
                    media_info.over_edition = over_edition
                    # 将当前的优先级传入检索
                    media_info.res_order = self._tv_repo.get_filter_order(rssid=rssid)
                # 开始检索
                filter_dict = {
                    "restype": rss_info.get("filter_restype"),
                    "pix": rss_info.get("filter_pix"),
                    "team": rss_info.get("filter_team"),
                    "rule": rss_info.get("filter_rule"),
                    "include": rss_info.get("filter_include"),
                    "exclude": rss_info.get("filter_exclude"),
                    "site": rss_info.get("search_sites"),
                }
                search_result, no_exists, _, _ = self._searcher.search_one_media(
                    media_info=media_info,
                    in_from=SearchType.RSS,
                    no_exists=rss_no_exists,
                    sites=rss_info.get("search_sites"),
                    filters=filter_dict,
                )
                if over_edition:
                    if search_result:
                        if self._service:
                            self._service.update_subscribe_over_edition(
                                rtype=media_info.type, rssid=rssid, media=search_result
                            )
                    else:
                        self._tv_repo.update_state(title=None, year=None, season=None, rssid=rssid, state="R")
                elif not no_exists or not no_exists.get(media_info.tmdb_id):
                    # 原始缺失为空，完成订阅
                    if self._service:
                        self._service.finish_rss_subscribe(rssid=rssid, media=media_info)
                elif search_result:
                    # 有下载但原始缺失非空，重新检查媒体库确认下载是否已覆盖全部缺失
                    exist_flag, library_no_exists, _ = self._downloader.check_exists_medias(
                        meta_info=media_info, total_ep={season: total_ep}
                    )
                    if not library_no_exists or not library_no_exists.get(media_info.tmdb_id):
                        if self._service:
                            self._service.finish_rss_subscribe(rssid=rssid, media=media_info)
                    else:
                        if self._service:
                            self._service.update_subscribe_tv_lack(
                                rssid=rssid, media_info=media_info, seasoninfo=library_no_exists.get(media_info.tmdb_id)
                            )
                elif no_exists:
                    # 没有下载，更新缺失状态
                    if self._service:
                        self._service.update_subscribe_tv_lack(
                            rssid=rssid, media_info=media_info, seasoninfo=no_exists.get(media_info.tmdb_id)
                        )
            except Exception as err:
                log.error(f"[Subscribe]电视剧 {name} 订阅搜索失败：{str(err)}")
                log.debug(f"异常详细信息: {traceback.format_exc()}")
                self._tv_repo.update_state(title=None, year=None, season=None, rssid=rssid, state="R")
                continue

    def __get_media_info(self, tmdbid, name, year, mtype, cache=True):
        """
        综合返回媒体信息
        """
        if tmdbid and not str(tmdbid).startswith("DB:"):
            media_info = meta_info(title="%s %s".strip() % (name, year))
            tmdb_info = self._media_cache.get_tmdb_info(mtype=mtype, tmdbid=tmdbid)
            media_info.set_tmdb_info(tmdb_info)
        else:
            media_info = self._media_service.identify(title=f"{name} {year}", mtype=mtype)
        return media_info

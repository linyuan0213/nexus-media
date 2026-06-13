"""基础搜索策略 — 提取 subscribe_search_engine 公共逻辑."""

import traceback
from typing import Any

import log
from app.core.exceptions import (
    DownloadError,
    IndexerError,
    MediaError,
    NetworkError,
    RepositoryError,
    ServiceError,
)
from app.db.repositories.subscribe_repo_adapter import (
    SubscribeMovieRepositoryAdapter,
    SubscribeTvEpisodeRepositoryAdapter,
    SubscribeTvRepositoryAdapter,
)
from app.db.repositories.subscribe_repository import SubscribeRepository
from app.domain.enums import SearchType
from app.domain.interfaces.rss_repo import (
    ISubscribeMovieRepository,
    ISubscribeTvEpisodeRepository,
    ISubscribeTvRepository,
)
from app.domain.mediatypes import MediaType
from app.media import MediaCache, MediaService, meta_info
from app.message import Message
from app.services.downloader_core import DownloaderCore as Downloader
from app.services.filter_service import FilterService as Filter
from app.services.search_service import Searcher
from app.services.subscribe.coordinator import DownloadCoordinator
from app.sites.torrent import Torrent


class BaseSearchStrategy:
    """搜索策略基类 — 封装 movie/tv 的公共搜索/下载逻辑."""

    _movie_repo: ISubscribeMovieRepository
    _tv_repo: ISubscribeTvRepository
    _tv_episode_repo: ISubscribeTvEpisodeRepository

    def __init__(
        self,
        service: Any,
        searcher: Searcher,
        media_service: MediaService,
        media_cache: MediaCache,
        downloader: Downloader,
        filter_service: Filter,
        message: Message,
        rss_repo: SubscribeRepository | None = None,
        movie_repo: ISubscribeMovieRepository | None = None,
        tv_repo: ISubscribeTvRepository | None = None,
        tv_episode_repo: ISubscribeTvEpisodeRepository | None = None,
        coordinator: DownloadCoordinator | None = None,
    ):
        self._service = service
        self._rss_repo = rss_repo or SubscribeRepository()
        if movie_repo is None:
            movie_repo = SubscribeMovieRepositoryAdapter(self._rss_repo)
        if tv_repo is None:
            tv_repo = SubscribeTvRepositoryAdapter(self._rss_repo)
        if tv_episode_repo is None:
            tv_episode_repo = SubscribeTvEpisodeRepositoryAdapter(self._rss_repo)
        self._movie_repo = movie_repo
        self._tv_repo = tv_repo
        self._tv_episode_repo = tv_episode_repo

        self._searcher = searcher
        self._coordinator = coordinator
        self._media_service = media_service
        self._media_cache = media_cache
        self._downloader = downloader
        self._filter = filter_service
        self._message = message

    def set_coordinator(self, coordinator: DownloadCoordinator | None) -> None:
        """设置下载协调器（用于 SubscriptionMonitor 注入）."""
        self._coordinator = coordinator

    def _search_movies(self, state: str = "D", rssid: int | None = None) -> None:
        if rssid:
            rss_movies = self._service.get_subscribe_movies(rid=rssid) if self._service else {}
        else:
            rss_movies = self._service.get_subscribe_movies(state=state) if self._service else {}
        if rss_movies:
            log.info(f"[Subscribe]共有 {len(rss_movies)} 个{MediaType.MOVIE.display_name}订阅需要搜索")
        for rss_info in rss_movies.values():
            if rss_info.get("fuzzy_match"):
                continue
            rssid = rss_info.get("id")
            name = rss_info.get("name")
            year = rss_info.get("year") or ""
            tmdbid = rss_info.get("tmdbid")
            over_edition = rss_info.get("over_edition")
            keyword = rss_info.get("keyword")

            self._movie_repo.update_state(title=None, year=None, rssid=rssid, state="S")
            media_info = None

            try:
                media_info = self._get_media_info(tmdbid, name, year, MediaType.MOVIE)
                if not media_info or not media_info.tmdb_info:
                    log.warn(f"[Subscribe]{MediaType.MOVIE.display_name} {name} TMDB 识别失败，标记为错误状态")
                    self._movie_repo.update_state(title=None, year=None, rssid=rssid, state="E")
                    continue
                media_info.set_download_info(
                    download_setting=rss_info.get("download_setting"), save_path=rss_info.get("save_path")
                )
                media_info.keyword = keyword
                if not over_edition:
                    exist_flag, no_exists, _ = self._downloader.check_exists_medias(meta_info=media_info)
                    if exist_flag:
                        log.info(f"[Subscribe]{MediaType.MOVIE.display_name} {media_info.get_title_string()} 已存在")
                        if self._service:
                            self._service.finish_rss_subscribe(rssid=rssid, media=media_info)
                        continue
                else:
                    no_exists = {}
                    media_info.over_edition = over_edition
                    if rssid is not None:
                        media_info.res_order = self._movie_repo.get_filter_order(rssid=rssid)

                if self._coordinator and not self._coordinator.try_acquire(media_info):
                    log.info(f"[Subscribe]{MediaType.MOVIE.display_name} {name} 已被其他策略处理，跳过")
                    self._movie_repo.update_state(title=None, year=None, rssid=rssid, state="R")
                    continue

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
                    in_from=SearchType.SUBSCRIBE,
                    no_exists=no_exists,
                    sites=rss_info.get("search_sites"),
                    filters=filter_dict,
                )
                if search_result:
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
            except (MediaError, DownloadError, IndexerError, RepositoryError, ServiceError, NetworkError) as err:
                self._movie_repo.update_state(title=None, year=None, rssid=rssid, state="R")
                log.error(f"[Subscribe]{MediaType.MOVIE.display_name} {name} 订阅搜索失败：{err!s}")
                log.debug(f"异常详细信息: {traceback.format_exc()}")
                continue
            finally:
                if self._coordinator and media_info is not None:
                    self._coordinator.release(media_info)

    def _search_tvs(self, state: str = "D", rssid: int | None = None) -> None:
        if rssid:
            rss_tvs = self._service.get_subscribe_tvs(rid=rssid) if self._service else {}
        else:
            rss_tvs = self._service.get_subscribe_tvs(state=state) if self._service else {}
        if rss_tvs:
            log.info(f"[Subscribe]共有 {len(rss_tvs)} 个{MediaType.TV.display_name}订阅需要检索")
        rss_no_exists = {}
        for rss_info in rss_tvs.values():
            if rss_info.get("fuzzy_match"):
                continue
            rssid = rss_info.get("id")
            name = rss_info.get("name")
            year = rss_info.get("year") or ""
            tmdbid = rss_info.get("tmdbid")
            over_edition = rss_info.get("over_edition")
            keyword = rss_info.get("keyword")

            self._tv_repo.update_state(title=None, year=None, season=None, rssid=rssid, state="S")
            media_info = None

            try:
                media_info = self._get_media_info(tmdbid, name, year, MediaType.TV)
                if not media_info or not media_info.tmdb_info:
                    log.warn(f"[Subscribe]{MediaType.TV.display_name} {name} TMDB 识别失败，标记为错误状态")
                    self._tv_repo.update_state(title=None, year=None, season=None, rssid=rssid, state="E")
                    continue
                media_info.set_download_info(
                    download_setting=rss_info.get("download_setting"), save_path=rss_info.get("save_path")
                )
                season = 1
                if rss_info.get("season"):
                    season = int(str(rss_info.get("season")).replace("S", ""))
                media_info.begin_season = season
                media_info.rssid = rssid
                total_ep = rss_info.get("total")
                current_ep = rss_info.get("current_ep")
                media_info.keyword = keyword
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
                if not over_edition:
                    exist_flag, library_no_exists, _ = self._downloader.check_exists_medias(
                        meta_info=media_info, total_ep={season: total_ep}
                    )
                    if exist_flag:
                        if not library_no_exists or not library_no_exists.get(media_info.tmdb_id):
                            log.info(
                                f"[Subscribe]{MediaType.TV.display_name} "
                                f"{media_info.get_title_string()} 订阅剧集已全部存在"
                            )
                            if self._service:
                                self._service.finish_rss_subscribe(rssid=rss_info.get("id"), media=media_info)
                        continue
                    rss_no_exists = Torrent.get_intersection_episodes(
                        target=rss_no_exists, source=library_no_exists, title=media_info.tmdb_id
                    )
                    if rss_no_exists.get(media_info.tmdb_id):
                        missing = rss_no_exists.get(media_info.tmdb_id)
                        log.info(f"[Subscribe]{media_info.get_title_string()} 订阅缺失季集：{missing}")
                else:
                    media_info.over_edition = over_edition
                    if rssid is not None:
                        media_info.res_order = self._tv_repo.get_filter_order(rssid=rssid)

                if self._coordinator and not self._coordinator.try_acquire(media_info):
                    log.info(f"[Subscribe]{MediaType.TV.display_name} {name} 已被其他策略处理，跳过")
                    self._tv_repo.update_state(title=None, year=None, season=None, rssid=rssid, state="R")
                    continue

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
                    in_from=SearchType.SUBSCRIBE,
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
                    if self._service:
                        self._service.finish_rss_subscribe(rssid=rssid, media=media_info)
                elif search_result:
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
                elif no_exists and self._service:
                    self._service.update_subscribe_tv_lack(
                        rssid=rssid, media_info=media_info, seasoninfo=no_exists.get(media_info.tmdb_id)
                    )
            except (MediaError, DownloadError, IndexerError, RepositoryError, ServiceError, NetworkError) as err:
                log.error(f"[Subscribe]{MediaType.TV.display_name} {name} 订阅搜索失败：{err!s}")
                log.debug(f"异常详细信息: {traceback.format_exc()}")
                self._tv_repo.update_state(title=None, year=None, season=None, rssid=rssid, state="R")
                continue
            finally:
                if self._coordinator and media_info is not None:
                    self._coordinator.release(media_info)

    def _get_media_info(self, tmdbid, name, year, mtype, cache=True):
        if tmdbid and not str(tmdbid).startswith("DB:"):
            media_info = meta_info(title="%s %s".strip() % (name, year))
            tmdb_info = self._media_cache.get_tmdb_info(mtype=mtype, tmdbid=tmdbid)
            media_info.set_tmdb_info(tmdb_info)
            if not (hasattr(media_info, "get_poster_image") and media_info.get_poster_image()):
                log.debug(f"[BaseSearchStrategy] 缓存缺少海报，重新识别: {name} ({year})")
                identified = self._media_service.identify(title=f"{name} {year}", mtype=mtype)
                if identified and hasattr(identified, "get_poster_image") and identified.get_poster_image():
                    media_info = identified
        else:
            media_info = self._media_service.identify(title=f"{name} {year}", mtype=mtype)
        return media_info

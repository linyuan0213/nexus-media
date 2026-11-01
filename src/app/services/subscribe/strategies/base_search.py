"""基础搜索策略 — 提取 subscribe_search_engine 公共逻辑."""

import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
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
from app.core.settings import settings
from app.db.repositories.subscribe_repo_adapter import (
    SubscribeMovieRepositoryAdapter,
    SubscribeTvEpisodeRepositoryAdapter,
    SubscribeTvRepositoryAdapter,
)
from app.db.repositories.subscribe_repository import SubscribeRepository
from app.domain.entities.rss import SubscribeState
from app.domain.enums import SearchType, SystemConfigKey
from app.domain.interfaces.rss_repo import (
    ISubscribeMovieRepository,
    ISubscribeTvEpisodeRepository,
    ISubscribeTvRepository,
)
from app.domain.media_ref import media_identity_key
from app.domain.mediatypes import MediaType
from app.infrastructure.cache_system import get_cache_manager
from app.media import MediaCache, MediaService, meta_info
from app.message import Message
from app.services.downloader_core import DownloaderCore as Downloader
from app.services.filter_service import FilterService as Filter
from app.services.search_service import Searcher
from app.services.subscribe.coordinator import DownloadCoordinator
from app.sites.torrent import Torrent

# 订阅搜索每轮处理上限（subscribe.batch_limit 可覆盖）
_SUBSCRIBE_BATCH_DEFAULT = 20


class BaseSearchStrategy:
    """搜索策略基类 — 封装 movie/tv 的公共搜索/下载逻辑."""

    _movie_repo: ISubscribeMovieRepository
    _tv_repo: ISubscribeTvRepository
    _tv_episode_repo: ISubscribeTvEpisodeRepository

    LOCK_EXTEND_INTERVAL = 60

    @staticmethod
    def _seed_poster_from_subscription(media_info, rss_info: dict) -> None:
        """订阅行已有海报时同步到 MediaInfo，下载/通知链路无需再回查订阅."""
        if media_info is None:
            return
        image = str(rss_info.get("image") or "").strip()
        if image and not media_info.get_poster_image():
            media_info.poster_path = image

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
        system_config=None,
    ):
        self._service = service
        self._system_config = system_config
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
        self._ident_cache = get_cache_manager().get_or_create(
            "subscribe_ident", cache_type="memory", maxsize=1000, ttl=3600
        )

    def set_coordinator(self, coordinator: DownloadCoordinator | None) -> None:
        """设置下载协调器（用于 SubscriptionMonitor 注入）."""
        self._coordinator = coordinator

    @staticmethod
    def _get_batch_limit() -> int:
        """订阅搜索每轮处理上限（subscribe.batch_limit，默认 20）."""
        try:
            return max(1, int((settings.get("subscribe") or {}).get("batch_limit") or _SUBSCRIBE_BATCH_DEFAULT))
        except (ValueError, TypeError):
            return _SUBSCRIBE_BATCH_DEFAULT

    def search_pending(self) -> None:
        """触发一次队列搜索（处理 PENDING 订阅），供事件处理器调用."""
        self._search_movies(state=SubscribeState.PENDING.value)
        self._search_tvs(state=SubscribeState.PENDING.value)

    def search_retry(self) -> None:
        """重试 ERROR 状态的订阅."""
        self._search_movies(state=SubscribeState.ERROR.value)
        self._search_tvs(state=SubscribeState.ERROR.value)

    def _get_effective_search_sites(self, rss_info: dict, mtype: MediaType) -> list | None:
        """订阅有效搜索站点.

        优先级：订阅显式配置 → 全局默认设置 → None（不限制，由用户可见站点集合决定）。
        返回 None 表示搜索全部当前用户可见站点，避免"未配置即搜不到"。
        """
        sites = rss_info.get("search_sites") or []
        if sites:
            return sites
        if not self._system_config:
            return None
        try:
            if mtype in (MediaType.TV, MediaType.ANIME):
                key = SystemConfigKey.DefaultSubscribeSettingTV.value
            else:
                profile = str(rss_info.get("content_profile") or "").strip()
                key = SystemConfigKey.DefaultSubscribeSettingMOV.value
                if profile and profile != "default":
                    key = f"{key}::{profile}"
            default_setting = self._system_config.get(key)
            if not isinstance(default_setting, dict):
                return None
            return default_setting.get("search_sites") or None
        except Exception as e:
            log.debug(f"[Subscribe]读取默认订阅设置站点失败: {e}")
            return None

    @contextmanager
    def _lock_context(self, media_info):
        """持锁期间自动续期，并在退出时释放锁。"""
        if self._coordinator is None or media_info is None:
            yield
            return

        stop_event = threading.Event()

        def _extend_loop():
            while not stop_event.wait(self.LOCK_EXTEND_INTERVAL):
                try:
                    if self._coordinator is not None:
                        self._coordinator.extend(media_info)
                except Exception as e:
                    log.debug(f"[BaseSearchStrategy] 锁续期失败: {e}")

        thread = threading.Thread(target=_extend_loop, daemon=True)
        thread.start()
        try:
            yield
        finally:
            stop_event.set()
            thread.join(timeout=1)
            self._coordinator.release(media_info)

    def _search_movies(
        self, state: str = SubscribeState.PENDING.value, rssid: int | None = None, force: bool = False
    ) -> None:
        if rssid:
            rss_movies = self._service.get_subscribe_movies(rid=rssid) if self._service else {}
        else:
            rss_movies = self._service.get_subscribe_movies(state=state) if self._service else {}
        if not rss_movies:
            return
        log.info(f"[Subscribe]共有 {len(rss_movies)} 个{MediaType.MOVIE.display_name}订阅需要搜索")

        def _process_one(rss_info: dict) -> None:
            if rss_info.get("fuzzy_match"):
                return
            rid = rss_info.get("id")
            name_val = rss_info.get("name")
            year_val = rss_info.get("year") or ""
            tmdbid = rss_info.get("tmdbid")
            over_edition = rss_info.get("over_edition")
            keyword = rss_info.get("keyword")

            media_info = None
            try:
                is_external = (
                    self._is_external_ref(tmdbid)
                    or bool(rss_info.get("anchor_provider") and str(rss_info.get("anchor_provider")) != "tmdb")
                    or bool(rss_info.get("anchor_external_id"))
                    or str(rss_info.get("content_profile") or "default") not in ("", "default")
                )
                media_info = self._get_media_info(
                    tmdbid,
                    name_val,
                    year_val,
                    MediaType.MOVIE,
                    anchor_provider=rss_info.get("anchor_provider"),
                    anchor_external_id=rss_info.get("anchor_external_id"),
                    content_profile=str(rss_info.get("content_profile") or ""),
                )
                if media_info is not None:
                    self._seed_poster_from_subscription(media_info, rss_info)
                    if rss_info.get("content_profile"):
                        media_info.content_profile = str(rss_info.get("content_profile"))
                    media_info.anchor_provider = rss_info.get("anchor_provider")
                    media_info.anchor_external_id = rss_info.get("anchor_external_id")
                    media_info.identity_id = rss_info.get("identity_id")
                if not media_info or (not media_info.provider_data and not is_external):
                    log.warn(f"[Subscribe]{MediaType.MOVIE.display_name} {name_val} TMDB 识别失败，标记为错误状态")
                    self._movie_repo.update_state(title=None, year=None, rssid=rid, state=SubscribeState.ERROR.value)
                    return

                media_info.set_download_info(
                    download_setting=rss_info.get("download_setting"), save_path=rss_info.get("save_path")
                )
                media_info.user_id = rss_info.get("user_id")
                media_info.keyword = keyword

                # 手动刷新允许重下，但已入库的媒体绝不能再创建下载任务。
                if force and self._service and self._service.media_exists(media_info):
                    log.info(f"[Subscribe]{name_val} 已入库，忽略刷新重新下载")
                    self._service.finish_rss_subscribe(rssid=rid, media=media_info)
                    return

                if self._coordinator and not self._coordinator.try_acquire(media_info):
                    log.info(f"[Subscribe]{MediaType.MOVIE.display_name} {name_val} 已被其他策略处理，跳过")
                    self._movie_repo.update_state(title=None, year=None, rssid=rid, state=SubscribeState.RUNNING.value)
                    return

                with self._lock_context(media_info):
                    if not over_edition and not is_external:
                        exist_flag, no_exists, _ = self._downloader.check_exists_medias(meta_info=media_info)
                        if exist_flag:
                            log.info(
                                f"[Subscribe]{MediaType.MOVIE.display_name} {media_info.get_title_string()} 已存在"
                            )
                            if self._service:
                                self._service.finish_rss_subscribe(rssid=rid, media=media_info)
                            return
                    else:
                        no_exists = {}
                        media_info.over_edition = over_edition
                        if rid is not None:
                            media_info.res_order = self._movie_repo.get_filter_order(rssid=rid)

                    self._movie_repo.update_state(
                        title=None, year=None, rssid=rid, state=SubscribeState.SEARCHING.value
                    )

                    try:
                        filters = {
                            "restype": rss_info.get("filter_restype"),
                            "pix": rss_info.get("filter_pix"),
                            "team": rss_info.get("filter_team"),
                            "rule": rss_info.get("filter_rule"),
                            "include": rss_info.get("filter_include"),
                            "exclude": rss_info.get("filter_exclude"),
                            "free": rss_info.get("filter_free"),
                        }
                        search_result, _, _, downloaded_count = self._searcher.search_one_media(
                            media_info=media_info,
                            in_from=SearchType.SUBSCRIBE,
                            no_exists=no_exists,
                            sites=self._get_effective_search_sites(rss_info, MediaType.MOVIE),
                            filters=filters,
                            user_id=rss_info.get("user_id"),
                            force_download=force,
                        )
                        if over_edition:
                            if search_result:
                                if self._service:
                                    self._service.update_subscribe_over_edition(
                                        rtype=search_result.type, rssid=rid, media=search_result
                                    )
                            else:
                                self._movie_repo.update_state(
                                    title=None, year=None, rssid=rid, state=SubscribeState.RUNNING.value
                                )
                        elif search_result or downloaded_count:
                            # 已登记下载：标记待转移，等入库事件定稿（写历史/删订阅），
                            # 避免下载未完成或转移失败时订阅被提前删除。
                            self._movie_repo.update_state(
                                title=None, year=None, rssid=rid, state=SubscribeState.COMPLETED.value
                            )
                        else:
                            self._movie_repo.update_state(
                                title=None, year=None, rssid=rid, state=SubscribeState.RUNNING.value
                            )
                    except (
                        MediaError,
                        DownloadError,
                        IndexerError,
                        RepositoryError,
                        ServiceError,
                        NetworkError,
                    ):
                        self._movie_repo.update_state(
                            title=None, year=None, rssid=rid, state=SubscribeState.RUNNING.value
                        )
                        log.error(
                            f"[Subscribe]{MediaType.MOVIE.display_name} {name_val}"
                            f" 订阅搜索失败：{traceback.format_exc()}"
                        )
            except Exception:
                log.error(
                    f"[Subscribe]{MediaType.MOVIE.display_name} {name_val} 订阅处理失败：{traceback.format_exc()}"
                )
                if rid:
                    try:
                        self._movie_repo.update_state(
                            title=None, year=None, rssid=rid, state=SubscribeState.ERROR.value
                        )
                    except Exception as update_err:
                        log.debug(f"[Subscribe]设置 ERROR 状态失败 rssid={rid}: {update_err}")

        batch_limit = self._get_batch_limit()
        if len(rss_movies) > batch_limit:
            log.info(
                f"[Subscribe]订阅数 {len(rss_movies)} 超过单轮上限 {batch_limit}，"
                f"本轮流处理前 {batch_limit} 个，其余保持 PENDING 下一轮继续"
            )
        with ThreadPoolExecutor(max_workers=5) as executor:
            list(executor.map(_process_one, list(rss_movies.values())[:batch_limit]))

    def _search_tvs(
        self, state: str = SubscribeState.PENDING.value, rssid: int | None = None, force: bool = False
    ) -> None:
        if rssid:
            rss_tvs = self._service.get_subscribe_tvs(rid=rssid) if self._service else {}
        else:
            rss_tvs = self._service.get_subscribe_tvs(state=state) if self._service else {}
        if not rss_tvs:
            return
        log.info(f"[Subscribe]共有 {len(rss_tvs)} 个{MediaType.TV.display_name}订阅需要检索")

        def _process_one(rss_info: dict) -> None:
            if rss_info.get("fuzzy_match"):
                return
            rid = rss_info.get("id")
            name_val = rss_info.get("name")
            year_val = rss_info.get("year") or ""
            tmdbid = rss_info.get("tmdbid")
            over_edition = rss_info.get("over_edition")
            keyword = rss_info.get("keyword")

            try:
                media_info = self._get_media_info(
                    tmdbid,
                    name_val,
                    year_val,
                    MediaType.TV,
                    anchor_provider=rss_info.get("anchor_provider"),
                    anchor_external_id=rss_info.get("anchor_external_id"),
                    content_profile=str(rss_info.get("content_profile") or ""),
                )
                non_tmdb_anchor = (
                    bool(rss_info.get("anchor_provider") and rss_info.get("anchor_provider") != "tmdb")
                    or bool(rss_info.get("anchor_external_id"))
                    or str(tmdbid or "").startswith("DB:")
                    or self._is_external_ref(tmdbid)
                )
                if not media_info or (not media_info.provider_data and not non_tmdb_anchor):
                    log.warn(f"[Subscribe]{MediaType.TV.display_name} {name_val} TMDB 识别失败，标记为错误状态")
                    self._tv_repo.update_state(
                        title=None, year=None, season=None, rssid=rid, state=SubscribeState.ERROR.value
                    )
                    return

                self._seed_poster_from_subscription(media_info, rss_info)
                media_info.set_download_info(
                    download_setting=rss_info.get("download_setting"), save_path=rss_info.get("save_path")
                )
                media_info.user_id = rss_info.get("user_id")
                season = 1
                if rss_info.get("season"):
                    season = int(str(rss_info.get("season")).replace("S", ""))
                media_info.begin_season = season
                media_info.rssid = rid
                total_ep = rss_info.get("total")
                current_ep = rss_info.get("current_ep")

                # 懒更新：TMDB 集数增加时自动同步（优先季详情集数，episode_count 常滞后）
                if rid:
                    try:
                        new_total = 0
                        try:
                            if media_info.provider_data:
                                season_detail = self._media_service.get_tmdb_tv_season_detail(
                                    media_info.tmdb_id, season
                                )
                                season_eps = season_detail.get("episodes") if isinstance(season_detail, dict) else None
                                if isinstance(season_eps, list):
                                    new_total = len(season_eps)
                        except Exception:  # noqa: BLE001
                            new_total = 0
                        if new_total <= 0 and media_info.provider_data:
                            new_total = int(
                                self._media_service.get_tmdb_season_episodes_num(
                                    tv_info=media_info.provider_data, season=season
                                )
                                or 0
                            )
                        if new_total > 0 and (total_ep is None or new_total > total_ep):
                            log.info(f"[Subscribe]{name_val} S{season} TMDB 总集数更新: {total_ep or 0} -> {new_total}")
                            old_total = int(total_ep or 0)
                            total_ep = int(new_total)
                            new_missing = list(range(old_total + 1, int(new_total) + 1))
                            self._tv_repo.update_total(rssid=rid, total_ep=int(new_total), lack_episodes=new_missing)
                    except Exception as e:  # noqa: BLE001
                        log.debug(f"[Subscribe]{name_val} TMDB 集数检查异常: {e}")
                media_info.keyword = keyword

                episodes = self._tv_episode_repo.get(rid) if rid is not None else None
                if episodes is None:
                    episodes_list = []
                    if current_ep and total_ep is not None:
                        episodes_list = list(range(current_ep, total_ep + 1))
                    elif total_ep is not None and total_ep > 0:
                        tep: int = total_ep
                        episodes_list = list(range(1, tep + 1))
                else:
                    episodes_list = episodes

                media_key = media_identity_key(media_info) or media_info.tmdb_id
                rss_no_exists_local = {
                    media_key: [{"season": season, "episodes": episodes_list, "total_episodes": total_ep}]
                }

                if self._coordinator and not self._coordinator.try_acquire(media_info):
                    log.info(f"[Subscribe]{MediaType.TV.display_name} {name_val} 已被其他策略处理，跳过")
                    self._tv_repo.update_state(
                        title=None, year=None, season=None, rssid=rid, state=SubscribeState.RUNNING.value
                    )
                    return

                with self._lock_context(media_info):
                    if not over_edition:
                        exist_flag, library_no_exists, _ = self._downloader.check_exists_medias(
                            meta_info=media_info, total_ep={season: total_ep}
                        )
                        if exist_flag:
                            if not library_no_exists or not library_no_exists.get(media_key):
                                log.info(
                                    f"[Subscribe]{MediaType.TV.display_name}"
                                    f" {media_info.get_title_string()} 订阅剧集已全部存在"
                                )
                                if self._service:
                                    self._service.finish_rss_subscribe(rssid=rss_info.get("id"), media=media_info)
                            return
                        rss_no_exists_local = Torrent.get_intersection_episodes(
                            target=rss_no_exists_local, source=library_no_exists, title=media_key
                        )
                        if rss_no_exists_local.get(media_key):
                            missing = rss_no_exists_local.get(media_key)
                            log.info(f"[Subscribe]{media_info.get_title_string()} 订阅缺失季集：{missing}")
                            if self._service:
                                self._service.update_subscribe_tv_lack(
                                    rssid=rid, media_info=media_info, seasoninfo=missing
                                )
                    else:
                        media_info.over_edition = over_edition
                        if rid is not None:
                            media_info.res_order = self._tv_repo.get_filter_order(rssid=rid)

                    self._tv_repo.update_state(
                        title=None, year=None, season=None, rssid=rid, state=SubscribeState.SEARCHING.value
                    )
                    # 搜索站点：订阅未配置时回退到默认订阅设置的 search_sites（与手动搜索一致）。
                    # 不能直接用 rss_info.get("search_sites")，否则空列表会覆盖 effective sites → 0 站点搜索
                    sites = self._get_effective_search_sites(rss_info, MediaType.TV)
                    filters_tv = {
                        "restype": rss_info.get("filter_restype"),
                        "pix": rss_info.get("filter_pix"),
                        "team": rss_info.get("filter_team"),
                        "rule": rss_info.get("filter_rule"),
                        "include": rss_info.get("filter_include"),
                        "exclude": rss_info.get("filter_exclude"),
                        "free": rss_info.get("filter_free"),
                    }
                    search_result, no_exists, _, _ = self._searcher.search_one_media(
                        media_info=media_info,
                        in_from=SearchType.SUBSCRIBE,
                        no_exists=rss_no_exists_local,
                        sites=sites,
                        filters=filters_tv,
                        user_id=rss_info.get("user_id"),
                    )
                    if over_edition:
                        if search_result:
                            if self._service:
                                self._service.update_subscribe_over_edition(
                                    rtype=media_info.type, rssid=rid, media=search_result
                                )
                        else:
                            self._tv_repo.update_state(
                                title=None, year=None, season=None, rssid=rid, state=SubscribeState.RUNNING.value
                            )
                    else:
                        # 完成判定只认「正向证据」：媒体库确认整季已存在（exist_flag=True）。
                        # 不可用 library_no_exists 为空来判定完成——当 TMDB 集数未知 / 媒体库目录尚不存在 /
                        # 无转移历史时，check_exists_medias 会返回 (False, {}, ...)，那是“无法确认”而非“已完成”。
                        exist_flag, library_no_exists, _ = self._downloader.check_exists_medias(
                            meta_info=media_info, total_ep={season: total_ep}
                        )
                        if exist_flag:
                            if self._service:
                                self._service.finish_rss_subscribe(rssid=rid, media=media_info)
                        elif library_no_exists and library_no_exists.get(media_key):
                            if self._service:
                                self._service.update_subscribe_tv_lack(
                                    rssid=rid,
                                    media_info=media_info,
                                    seasoninfo=library_no_exists.get(media_key),
                                )
                        elif no_exists and no_exists.get(media_key):
                            if self._service:
                                self._service.update_subscribe_tv_lack(
                                    rssid=rid, media_info=media_info, seasoninfo=no_exists.get(media_key)
                                )
                        else:
                            log.info(f"[Subscribe]{media_info.get_title_string()} 订阅完成情况无法确认，保持运行")
                            self._tv_repo.update_state(
                                title=None, year=None, season=None, rssid=rid, state=SubscribeState.RUNNING.value
                            )
            except (MediaError, DownloadError, IndexerError, RepositoryError, ServiceError, NetworkError):
                log.error(f"[Subscribe]{MediaType.TV.display_name} {name_val} 订阅搜索失败：{traceback.format_exc()}")
                self._tv_repo.update_state(
                    title=None, year=None, season=None, rssid=rid, state=SubscribeState.RUNNING.value
                )
            except Exception:
                log.error(f"[Subscribe]{MediaType.TV.display_name} {name_val} 订阅处理失败：{traceback.format_exc()}")
                self._tv_repo.update_state(
                    title=None, year=None, season=None, rssid=rid, state=SubscribeState.ERROR.value
                )

        batch_limit = self._get_batch_limit()
        if len(rss_tvs) > batch_limit:
            log.info(
                f"[Subscribe]订阅数 {len(rss_tvs)} 超过单轮上限 {batch_limit}，"
                f"本轮流处理前 {batch_limit} 个，其余保持 PENDING 下一轮继续"
            )
        with ThreadPoolExecutor(max_workers=5) as executor:
            list(executor.map(_process_one, list(rss_tvs.values())[:batch_limit]))

    @staticmethod
    def _is_external_ref(value) -> bool:
        """插件 provider 引用（如 content_id:START-660）不是 TMDB ID."""
        text = str(value or "")
        if ":" not in text:
            return False
        prefix = text.split(":", 1)[0].strip().upper()
        return prefix not in {"DB", "TMDB", "DOUBAN", "BANGUMI", "BGM", "BG"}

    def _get_media_info(
        self,
        tmdbid,
        name,
        year,
        mtype,
        cache=True,
        anchor_provider=None,
        anchor_external_id=None,
        content_profile: str = "",
    ):
        """综合返回媒体信息；非 TMDB 来源不查询 TMDB."""
        key = (
            f"ident:{mtype}:{name or ''}:{year or ''}:{tmdbid or ''}:{anchor_provider or ''}:"
            f"{anchor_external_id or ''}:{content_profile or ''}"
        )
        cached = self._ident_cache.get(key)
        if cached is not None:
            return cached

        if anchor_provider and anchor_provider != "tmdb" and anchor_external_id:
            media_info = meta_info(title=("%s %s" % (name, year)).strip(), mtype=mtype)
            media_info.tmdb_id = ""
            media_info.anchor_provider = str(anchor_provider)
            media_info.anchor_external_id = str(anchor_external_id)
            if anchor_provider == "douban":
                media_info.douban_id = str(anchor_external_id)
            media_info.type = mtype
            media_info.title = name or media_info.title
            media_info.cn_name = name or media_info.cn_name
            media_info.year = year or media_info.year
            # 核心画像（default/anime）可用 TMDB 补充海报/简介；插件画像由插件负责。
            raw_tmdb = str(tmdbid or "").strip()
            if raw_tmdb.isdigit() and str(content_profile or "").strip().lower() in ("", "default", "anime"):
                media_info.tmdb_id = raw_tmdb
                media_info.provider_data = self._media_cache.get_tmdb_info(mtype=mtype, tmdbid=raw_tmdb) or {}
        elif self._is_external_ref(tmdbid):
            media_info = meta_info(title=("%s %s" % (name, year)).strip(), mtype=mtype)
            media_info.tmdb_id = ""
            media_info.anchor_provider = str(tmdbid).split(":", 1)[0].lower()
            media_info.anchor_external_id = str(tmdbid).split(":", 1)[-1]
            media_info.type = mtype
        elif str(tmdbid or "").startswith("DB:"):
            # 豆瓣锚点不再走 TMDB identify；直接按豆瓣标题/年份构造搜索媒体
            media_info = meta_info(title=("%s %s" % (name, year)).strip(), mtype=mtype)
            media_info.tmdb_id = ""
            media_info.douban_id = str(tmdbid)[3:]
            media_info.anchor_provider = "douban"
            media_info.anchor_external_id = str(tmdbid)[3:]
            media_info.type = mtype
            media_info.title = name or media_info.title
            media_info.cn_name = name or media_info.cn_name
            media_info.year = year or media_info.year
        elif str(content_profile or "").strip().lower() not in ("", "default", "anime"):
            media_info = meta_info(title=("%s %s" % (name, year)).strip(), mtype=mtype)
            media_info.tmdb_id = ""
            media_info.type = mtype
            media_info.title = name or media_info.title
            media_info.cn_name = name or media_info.cn_name
            media_info.year = year or media_info.year
        elif tmdbid and not str(tmdbid).startswith("DB:"):
            media_info = meta_info(title=("%s %s" % (name, year)).strip())
            tmdb_info = self._media_cache.get_tmdb_info(mtype=mtype, tmdbid=tmdbid)
            media_info.set_provider_data(tmdb_info)
            # en_name 为空或非拉丁时补全英文名，避免日语原名导致英文标题匹配失败
            if self._media_service:
                self._media_service.enrich_en_name(media_info)
            if not media_info.provider_data or not (
                hasattr(media_info, "get_poster_image") and media_info.get_poster_image()
            ):
                log.debug(f"[BaseSearchStrategy] 缺少 TMDB 信息，重新识别: {name} ({year})")
                identified = self._media_service.identify(title=f"{name} {year}".strip(), mtype=mtype)
                if identified and getattr(identified, "provider_data", None):
                    media_info = identified
        else:
            media_info = self._media_service.identify(title=f"{name} {year}".strip(), mtype=mtype)

        if media_info is not None:
            self._ident_cache.set(key, media_info)
        return media_info

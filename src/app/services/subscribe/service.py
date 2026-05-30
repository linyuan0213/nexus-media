"""Subscribe service - 订阅业务 Facade."""

import log
from app.db.repositories.rss_repo_adapter import (
    RssHistoryRepositoryAdapter,
    RssMovieRepositoryAdapter,
    RssTvEpisodeRepositoryAdapter,
    RssTvRepositoryAdapter,
)
from app.di import container
from app.domain.entities.rss import SubscribeState
from app.services.subscribe.add_service import SubscribeAddService
from app.services.subscribe.finish_service import SubscribeFinishService
from app.services.subscribe.query_service import SubscribeQueryService
from app.services.subscribe.refresh_service import SubscribeRefreshService
from app.services.subscribe.update_service import SubscribeUpdateService
from app.services.subscribe_search_engine import SubscribeSearchEngine
from app.utils.types import MediaType, SystemConfigKey


class SubscribeService:
    """订阅业务 Facade - 保留与原 Subscribe 兼容的公共 API"""

    def __init__(
        self,
        movie_repo=None,
        tv_repo=None,
        tv_episode_repo=None,
        history_repo=None,
        search_engine: SubscribeSearchEngine | None = None,
        message=None,
        media_service=None,
        downloader=None,
        sites=None,
        douban=None,
        indexer_service=None,
        filter_service=None,
        event_bus=None,
        system_config=None,
    ):
        self._movie_repo = movie_repo or RssMovieRepositoryAdapter()
        self._tv_repo = tv_repo or RssTvRepositoryAdapter()
        self._tv_episode_repo = tv_episode_repo or RssTvEpisodeRepositoryAdapter()
        self._history_repo = history_repo or RssHistoryRepositoryAdapter()
        self._message = message or container.message()
        self._media = media_service or container.media_service()
        self._downloader = downloader or container.downloader_core()
        self._sites = sites or container.sites()
        self._douban = douban or container.douban()
        self._indexer_service = indexer_service or container.indexer_service()
        self._filter = filter_service or container.filter_service()
        self._event_bus = event_bus or container.event_bus()
        self._system_config = system_config or container.system_config()

        self._update_svc = SubscribeUpdateService(
            self._movie_repo, self._tv_repo, self._media, self._message, self._event_bus, self._system_config
        )
        self._add_svc = SubscribeAddService(
            self._movie_repo, self._tv_repo, self._media, self._message, self._event_bus, self._system_config
        )
        self._finish_svc = SubscribeFinishService(
            self._movie_repo, self._tv_repo, self._history_repo, self._message, self._event_bus
        )
        self._query_svc = SubscribeQueryService(
            self._movie_repo,
            self._tv_repo,
            self._tv_episode_repo,
            self._history_repo,
            self._sites,
            self._indexer_service,
        )
        self._refresh_svc = SubscribeRefreshService(self._movie_repo, self._tv_repo, self._tv_episode_repo, self._media)
        self._search_engine = search_engine or SubscribeSearchEngine(
            service=self, movie_repo=self._movie_repo, tv_repo=self._tv_repo, tv_episode_repo=self._tv_episode_repo
        )

    @property
    def default_rss_setting_tv(self) -> dict | None:
        return self._system_config.get(SystemConfigKey.DefaultRssSettingTV) or {}

    @property
    def default_rss_setting_mov(self) -> dict | None:
        return self._system_config.get(SystemConfigKey.DefaultRssSettingMOV) or {}

    def update_rss_subscribe(self, *args, **kwargs):
        return self._update_svc.update_rss_subscribe(*args, **kwargs)

    def add_rss_subscribe(self, *args, **kwargs):
        return self._add_svc.add_rss_subscribe(*args, **kwargs)

    def finish_rss_subscribe(self, rssid, media):
        return self._finish_svc.finish_rss_subscribe(rssid, media, self.delete_subscribe)

    def get_subscribe_movies(self, rid=None, state=None):
        return self._query_svc.get_subscribe_movies(rid, state)

    def get_subscribe_tvs(self, rid=None, state=None):
        return self._query_svc.get_subscribe_tvs(rid, state)

    def get_subscribe_tv_episodes(self, rssid):
        return self._query_svc.get_subscribe_tv_episodes(rssid)

    def check_history(self, type_str, name, year=None, season=None):
        return self._query_svc.check_history(type_str, name, year, season)

    def delete_subscribe(self, mtype, title=None, year=None, season=None, rssid=None, tmdbid=None):
        return self._query_svc.delete_subscribe(mtype, title, year, season, rssid, tmdbid)

    def get_subscribe_id(self, mtype, title, year=None, season=None, tmdbid=None):
        return self._query_svc.get_subscribe_id(mtype, title, year, season, tmdbid)

    def refresh_rss_metainfo(self):
        return self._refresh_svc.refresh_rss_metainfo(self.get_subscribe_movies, self.get_subscribe_tvs)

    def subscribe_search_all(self):
        self._search_engine.subscribe_search_all()

    def subscribe_search(self, state="D"):
        self._search_engine.subscribe_search(state=state)

    def subscribe_search_movie(self, rssid=None, state="D"):
        self._search_engine.subscribe_search_movie(rssid=rssid, state=state)

    def subscribe_search_tv(self, rssid=None, state="D"):
        self._search_engine.subscribe_search_tv(rssid=rssid, state=state)

    def update_rss_state(self, rtype, rssid, state):
        if rtype == MediaType.MOVIE:
            movies = self._movie_repo.get_all(rssid=rssid)
            if not movies:
                return
            entity = movies[0]
            if state == SubscribeState.RUNNING.value:
                entity.mark_running()
            elif state == SubscribeState.COMPLETED.value:
                entity.mark_completed()
            elif state == SubscribeState.CANCELLED.value:
                entity.mark_cancelled()
            elif state == SubscribeState.PENDING.value:
                entity.state = SubscribeState.PENDING.value
            self._movie_repo.update(rssid=rssid, state=entity.state)
        else:
            tvs = self._tv_repo.get_all(rssid=rssid)
            if not tvs:
                return
            entity = tvs[0]
            if state == SubscribeState.RUNNING.value:
                entity.mark_running()
            elif state == SubscribeState.COMPLETED.value:
                entity.mark_completed()
            elif state == SubscribeState.CANCELLED.value:
                entity.mark_cancelled()
            elif state == SubscribeState.PENDING.value:
                entity.state = SubscribeState.PENDING.value
            self._tv_repo.update(rssid=rssid, state=entity.state)

    def update_subscribe_over_edition(self, rtype, rssid, media):
        if not rssid or not media.res_order or not media.filter_rule:
            return False
        if rtype == MediaType.MOVIE:
            self._movie_repo.update_filter_order(rssid=rssid, res_order=media.res_order)
        else:
            self._tv_repo.update_filter_order(rssid=rssid, res_order=media.res_order)
        over_edition_order = self._filter.get_rule_first_order(rulegroup=media.filter_rule)
        if int(media.res_order) >= int(over_edition_order):
            self.finish_rss_subscribe(rssid=rssid, media=media)
            return True
        else:
            self.update_rss_state(rtype=rtype, rssid=rssid, state="R")
        return False

    def check_subscribe_over_edition(self, rtype, rssid, res_order):
        if rtype == MediaType.MOVIE:
            pre_res_order = self._movie_repo.get_filter_order(rssid=rssid)
        else:
            pre_res_order = self._tv_repo.get_filter_order(rssid=rssid)
        if not pre_res_order:
            return True
        return int(pre_res_order) < int(res_order or 0)

    def update_subscribe_tv_lack(self, rssid, media_info, seasoninfo):
        self._tv_repo.update_state(title=None, year=None, season=None, rssid=rssid, state="R")
        if not seasoninfo:
            return
        for info in seasoninfo:
            if str(info.get("season")) == media_info.get_season_seq():
                if info.get("episodes"):
                    log.info(
                        "[Subscribe]更新电视剧 {} {} 缺失集数为 {}".format(
                            media_info.get_title_string(), media_info.get_season_string(), len(info.get("episodes"))
                        )
                    )
                    self._tv_repo.update_lack(
                        title=None, year=None, season=None, rssid=rssid, lack_episodes=info.get("episodes")
                    )
                break

    def truncate_rss_episodes(self):
        self._tv_episode_repo.delete_all()

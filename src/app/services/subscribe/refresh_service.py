"""Subscribe refresh service - 刷新订阅TMDB信息."""

import log
from app.media import meta_info
from app.services.subscribe.utils import gen_rss_note
from app.utils.types import MediaType


class SubscribeRefreshService:
    """刷新订阅服务"""

    def __init__(self, movie_repo, tv_repo, tv_episode_repo, media_service):
        self._movie_repo = movie_repo
        self._tv_repo = tv_repo
        self._tv_episode_repo = tv_episode_repo
        self._media = media_service

    def refresh_rss_metainfo(self, get_subscribe_movies_fn, get_subscribe_tvs_fn) -> None:
        """定时将豆瓣订阅转换为TMDB的订阅，并更新订阅的TMDB信息"""
        log.info("【Subscribe】开始刷新订阅TMDB信息...")
        rss_movies = get_subscribe_movies_fn(state="R")
        for _rid, rss_info in rss_movies.items():
            if rss_info.get("fuzzy_match"):
                continue
            rssid = rss_info.get("id")
            name = rss_info.get("name")
            year = rss_info.get("year") or ""
            tmdbid = rss_info.get("tmdbid")
            if tmdbid:
                log.debug(f"【Subscribe】电影 {name} 已有 TMDB ID {tmdbid}，跳过刷新")
                continue
            media_info = self.__get_media_info(tmdbid=tmdbid, name=name, year=year, mtype=MediaType.MOVIE, cache=True)
            if media_info and media_info.tmdb_id and media_info.title != name:
                log.info(f"【Subscribe】检测到TMDB信息变化，更新电影订阅 {name} 为 {media_info.title}")
                self._movie_repo.update_tmdb(
                    rid=rssid,
                    tmdbid=str(media_info.tmdb_id or ""),
                    title=media_info.title or "",
                    year=media_info.year or "",
                    image=media_info.get_message_image(),
                    desc=media_info.overview or "",
                    note=gen_rss_note(media_info),
                )

        rss_tvs = get_subscribe_tvs_fn(state="R")
        for _rid, rss_info in rss_tvs.items():
            if rss_info.get("fuzzy_match"):
                continue
            rssid = rss_info.get("id")
            name = rss_info.get("name")
            year = rss_info.get("year") or ""
            tmdbid = rss_info.get("tmdbid")
            season = rss_info.get("season") or 1
            total = rss_info.get("total")
            total_ep = rss_info.get("total_ep")
            lack = rss_info.get("lack")
            if tmdbid:
                log.debug(f"【Subscribe】电视剧 {name} 已有 TMDB ID {tmdbid}，跳过刷新")
                continue
            media_info = self.__get_media_info(tmdbid=tmdbid, name=name, year=year, mtype=MediaType.TV, cache=True)
            if media_info and media_info.tmdb_id:
                total_episode = self._media.get_tmdb_season_episodes_num(
                    tv_info=media_info.tmdb_info, season=int(str(season).replace("S", ""))
                )
                if total_ep:
                    total_episode = total_ep
                if total_episode and (name != media_info.title or total != total_episode):
                    lack_episode = total_episode - (total - lack)
                    log.info(
                        f"【Subscribe】检测到TMDB信息变化，更新电视剧订阅 {name} 为 {media_info.title}，"
                        f"总集数为：{total_episode}"
                    )
                    self._tv_repo.update_tmdb(
                        rid=rssid,
                        tmdbid=str(media_info.tmdb_id or ""),
                        title=media_info.title or "",
                        year=media_info.year or "",
                        total=total_episode,
                        lack=lack_episode,
                        image=media_info.get_message_image(),
                        desc=media_info.overview or "",
                        note=gen_rss_note(media_info),
                    )
                    self._tv_episode_repo.update(
                        rid=rssid, episodes=list(range(total_episode - lack_episode + 1, total_episode + 1))
                    )
        log.info("【Subscribe】订阅TMDB信息刷新完成")

    def __get_media_info(self, tmdbid, name, year, mtype, cache=True):
        """综合返回媒体信息"""
        if tmdbid and not str(tmdbid).startswith("DB:"):
            media_info = meta_info(title="%s %s".strip() % (name, year))
            tmdb_info = self._media.get_tmdb_info(mtype=mtype, tmdbid=tmdbid)
            media_info.set_tmdb_info(tmdb_info)
        else:
            media_info = self._media.get_media_info(title=f"{name} {year}", mtype=mtype, strict=True, cache=cache)
        return media_info

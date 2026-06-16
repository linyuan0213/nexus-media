"""
RSS Repository
Handles RSS movies, TV shows, episodes and history related database operations.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from app.db.models import SubscribeHistory, SubscribeMovies, SubscribeTorrents, SubscribeTvEpisodes, SubscribeTvs
from app.db.repositories.base_repository import BaseRepository
from app.domain.mediatypes import MediaType
from app.utils.json_utils import JsonUtils

if TYPE_CHECKING:
    from app.media.models import MediaInfo


class SubscribeRepository(BaseRepository):
    """
    RSS订阅仓储
    处理RSS电影、电视剧、剧集和历史记录的数据库操作
    """

    def reset_rss_state(self) -> None:
        """
        初始化时批量重置所有 RSS 订阅状态
        将 STATE='S' 的订阅重置为 STATE='D'，由 SubscriptionMonitor 重新启动队列搜索
        """
        with self.session() as db:
            db.query(SubscribeMovies).filter(SubscribeMovies.STATE == "S").update(
                {"STATE": "D"}, synchronize_session=False
            )
            db.query(SubscribeTvs).filter(SubscribeTvs.STATE == "S").update({"STATE": "D"}, synchronize_session=False)

    # ==================== RSS Movies ====================

    def get_rss_movies(self, state: str | None = None, rssid: int | None = None) -> list[SubscribeMovies]:
        """
        查询订阅电影信息
        """
        with self.session() as db:
            if rssid:
                return db.query(SubscribeMovies).filter(int(rssid) == SubscribeMovies.ID).all()
            if not state:
                return db.query(SubscribeMovies).all()
            return db.query(SubscribeMovies).filter(state == SubscribeMovies.STATE).all()

    def get_rss_movie_id(self, title: str, year: str | None = None, tmdbid: str | None = None) -> int | str | None:
        """
        获取订阅电影ID
        """
        if not title:
            return None
        with self.session() as db:
            if tmdbid:
                ret = db.query(SubscribeMovies.ID).filter(str(tmdbid) == SubscribeMovies.TMDBID).first()
                if ret:
                    return ret[0]
            query = db.query(SubscribeMovies.ID).filter(title == SubscribeMovies.NAME)
            if year:
                query = query.filter(str(year) == SubscribeMovies.YEAR)
            ret = query.first()
            return ret[0] if ret else None

    def get_rss_tv_id(
        self, title: str, year: str | None = None, season: str | None = None, tmdbid: str | None = None
    ) -> int | str | None:
        """
        获取订阅电视剧ID
        """
        if not title:
            return None
        with self.session() as db:
            if tmdbid:
                query = db.query(SubscribeTvs.ID).filter(str(tmdbid) == SubscribeTvs.TMDBID)
                if season:
                    query = query.filter(str(season) == SubscribeTvs.SEASON)
                ret = query.first()
                if ret:
                    return ret[0]
            query = db.query(SubscribeTvs.ID).filter(title == SubscribeTvs.NAME)
            if season:
                query = query.filter(str(season) == SubscribeTvs.SEASON)
            if year:
                query = query.filter(str(year) == SubscribeTvs.YEAR)
            ret = query.first()
            return ret[0] if ret else None

    def get_subscribe_id(self, mtype, title, year, tmdbid) -> int | None:
        """
        查询订阅ID
        """
        if not title:
            return None
        if mtype == MediaType.MOVIE:
            result = self.get_rss_movie_id(title, year, tmdbid)
        else:
            result = self.get_rss_tv_id(title, year, tmdbid)
        return int(result) if isinstance(result, (int, str)) and str(result).isdigit() else None

    def get_rss_movie_sites(self, rssid: int | None) -> str:
        """
        获取订阅电影站点
        """
        if not rssid:
            return ""
        with self.session() as db:
            ret = db.query(SubscribeMovies.DESC).filter(int(rssid) == SubscribeMovies.ID).first()
            if ret:
                return ret[0]
            return ""

    def update_rss_movie_tmdb(
        self, rid: int, tmdbid: str, title: str, year: str, image: str, desc: str, note: str
    ) -> None:
        """
        更新订阅电影的部分信息
        """
        if not tmdbid:
            return
        with self.session() as db:
            db.query(SubscribeMovies).filter(int(rid) == SubscribeMovies.ID).update(
                {
                    "TMDBID": tmdbid,
                    "NAME": title,
                    "YEAR": year,
                    "IMAGE": image,
                    "NOTE": note,
                    "DESC": desc,
                }
            )

    def update_rss_movie_desc(self, rid: int, desc: str) -> None:
        """
        更新订阅电影的DESC
        """
        with self.session() as db:
            db.query(SubscribeMovies).filter(int(rid) == SubscribeMovies.ID).update({"DESC": desc})

    def update_rss_filter_order(self, rtype: str, rssid: int, res_order: str) -> None:
        """
        更新订阅命中的过滤规则优先级
        """
        with self.session() as db:
            if rtype == MediaType.MOVIE:
                db.query(SubscribeMovies).filter(int(rssid) == SubscribeMovies.ID).update({"FILTER_ORDER": res_order})
            else:
                db.query(SubscribeTvs).filter(int(rssid) == SubscribeTvs.ID).update({"FILTER_ORDER": res_order})

    def get_rss_overedition_order(self, rtype: str, rssid: int) -> int:
        """
        查询当前订阅的过滤优先级
        """
        with self.session() as db:
            if rtype == MediaType.MOVIE:
                res = db.query(SubscribeMovies.FILTER_ORDER).filter(int(rssid) == SubscribeMovies.ID).first()
            else:
                res = db.query(SubscribeTvs.FILTER_ORDER).filter(int(rssid) == SubscribeTvs.ID).first()
            if res and res[0]:
                return int(res[0])
            return 0

    def is_exists_rss_movie(self, title: str, year: str | None = None) -> bool:
        """
        判断RSS电影是否存在
        """
        if not title:
            return False
        with self.session() as db:
            if year is not None:
                count = (
                    db.query(SubscribeMovies)
                    .filter(title == SubscribeMovies.NAME, str(year) == SubscribeMovies.YEAR)
                    .count()
                )
            else:
                count = db.query(SubscribeMovies).filter(title == SubscribeMovies.NAME).count()
            return count > 0

    def insert_rss_movie(
        self,
        media_info: MediaInfo,
        state: str = "D",
        rss_sites: list | None = None,
        search_sites: list | None = None,
        over_edition: int = 0,
        filter_restype: str | None = None,
        filter_pix: str | None = None,
        filter_team: str | None = None,
        filter_rule: str | None = None,
        filter_include: str | None = None,
        filter_exclude: str | None = None,
        save_path: str | None = None,
        download_setting: int = -1,
        fuzzy_match: int = 0,
        desc: str | None = None,
        note: str | None = None,
        keyword: str | None = None,
    ) -> int:
        """
        新增RSS电影
        """
        if search_sites is None:
            search_sites = []
        if rss_sites is None:
            rss_sites = []
        if not media_info:
            return -1
        if not media_info.title:
            return -1

        with self.session() as db:
            if media_info.year is not None:
                count = (
                    db.query(SubscribeMovies)
                    .filter(media_info.title == SubscribeMovies.NAME, str(media_info.year) == SubscribeMovies.YEAR)
                    .count()
                )
            else:
                count = db.query(SubscribeMovies).filter(media_info.title == SubscribeMovies.NAME).count()
            if count > 0:
                return 9

            db.add(
                SubscribeMovies(
                    NAME=media_info.title,
                    YEAR=media_info.year,
                    TMDBID=media_info.tmdb_id,
                    IMAGE=media_info.get_message_image(),
                    RSS_SITES=JsonUtils.dumps(rss_sites),
                    SEARCH_SITES=JsonUtils.dumps(search_sites),
                    OVER_EDITION=over_edition,
                    FILTER_RESTYPE=filter_restype,
                    FILTER_PIX=filter_pix,
                    FILTER_RULE=filter_rule,
                    FILTER_TEAM=filter_team,
                    FILTER_INCLUDE=filter_include,
                    FILTER_EXCLUDE=filter_exclude,
                    SAVE_PATH=save_path,
                    DOWNLOAD_SETTING=download_setting,
                    FUZZY_MATCH=fuzzy_match,
                    STATE=state,
                    DESC=desc,
                    NOTE=note,
                    KEYWORD=keyword,
                )
            )
        return 0

    def update_rss_movie(self, rssid: int, **kwargs: str | int | list | None) -> int:
        """
        更新RSS电影订阅信息（根据rssid）
        """
        if not rssid:
            return -1
        update_fields = {}
        field_map = {
            "name": "NAME",
            "year": "YEAR",
            "tmdbid": "TMDBID",
            "image": "IMAGE",
            "rss_sites": "RSS_SITES",
            "search_sites": "SEARCH_SITES",
            "over_edition": "OVER_EDITION",
            "filter_restype": "FILTER_RESTYPE",
            "filter_pix": "FILTER_PIX",
            "filter_rule": "FILTER_RULE",
            "filter_team": "FILTER_TEAM",
            "filter_include": "FILTER_INCLUDE",
            "filter_exclude": "FILTER_EXCLUDE",
            "save_path": "SAVE_PATH",
            "download_setting": "DOWNLOAD_SETTING",
            "fuzzy_match": "FUZZY_MATCH",
            "state": "STATE",
            "desc": "DESC",
            "note": "NOTE",
            "keyword": "KEYWORD",
        }
        for k, v in kwargs.items():
            col = field_map.get(k)
            if col is not None:
                if k in ("rss_sites", "search_sites") and isinstance(v, list):
                    update_fields[col] = JsonUtils.dumps(v)
                else:
                    update_fields[col] = v
        if not update_fields:
            return 0
        with self.session() as db:
            db.query(SubscribeMovies).filter(int(rssid) == SubscribeMovies.ID).update(update_fields)
        return 0

    def delete_rss_movie(
        self, title: str | None = None, year: str | None = None, rssid: int | None = None, tmdbid: str | None = None
    ) -> None:
        """
        删除RSS电影
        """
        if not title and not rssid:
            return
        with self.session() as db:
            if rssid:
                db.query(SubscribeMovies).filter(int(rssid) == SubscribeMovies.ID).delete()
            else:
                if tmdbid:
                    db.query(SubscribeMovies).filter(tmdbid == SubscribeMovies.TMDBID).delete()
                db.query(SubscribeMovies).filter(
                    title == SubscribeMovies.NAME, str(year) == SubscribeMovies.YEAR
                ).delete()

    def update_rss_movie_state(
        self, title: str | None = None, year: str | None = None, rssid: int | None = None, state: str = "R"
    ) -> None:
        """
        更新电影订阅状态
        """
        if not title and not rssid:
            return
        with self.session() as db:
            if rssid:
                db.query(SubscribeMovies).filter(int(rssid) == SubscribeMovies.ID).update({"STATE": state})
            else:
                db.query(SubscribeMovies).filter(
                    title == SubscribeMovies.NAME, str(year) == SubscribeMovies.YEAR
                ).update({"STATE": state})

    # ==================== RSS TV Shows ====================

    def get_rss_tvs(self, state: str | None = None, rssid: int | None = None) -> list[SubscribeTvs]:
        """
        查询订阅电视剧信息
        """
        with self.session() as db:
            if rssid:
                return db.query(SubscribeTvs).filter(int(rssid) == SubscribeTvs.ID).all()
            if not state:
                return db.query(SubscribeTvs).all()
            return db.query(SubscribeTvs).filter(state == SubscribeTvs.STATE).all()

    def get_rss_tv_sites(self, rssid: int | None) -> SubscribeTvs | str:
        """
        获取订阅电视剧站点
        """
        if not rssid:
            return ""
        with self.session() as db:
            ret = db.query(SubscribeTvs).filter(int(rssid) == SubscribeTvs.ID).first()
            if ret:
                return ret
            return ""

    def update_rss_tv_tmdb(
        self, rid: int, tmdbid: str, title: str, year: str, total: int, lack: int, image: str, desc: str, note: str
    ) -> None:
        """
        更新订阅电视剧的TMDB信息
        """
        if not tmdbid:
            return
        with self.session() as db:
            db.query(SubscribeTvs).filter(int(rid) == SubscribeTvs.ID).update(
                {
                    "TMDBID": tmdbid,
                    "NAME": title,
                    "YEAR": year,
                    "TOTAL": total,
                    "LACK": lack,
                    "IMAGE": image,
                    "DESC": desc,
                    "NOTE": note,
                }
            )

    def update_rss_tv_desc(self, rid: int, desc: str) -> None:
        """
        更新订阅电视剧的DESC
        """
        with self.session() as db:
            db.query(SubscribeTvs).filter(int(rid) == SubscribeTvs.ID).update({"DESC": desc})

    def is_exists_rss_tv(self, title: str, year: str | None = None, season: str | None = None) -> bool:
        """
        判断RSS电视剧是否存在
        """
        if not title:
            return False
        with self.session() as db:
            if season:
                count = (
                    db.query(SubscribeTvs)
                    .filter(title == SubscribeTvs.NAME, str(year) == SubscribeTvs.YEAR, season == SubscribeTvs.SEASON)
                    .count()
                )
            else:
                count = (
                    db.query(SubscribeTvs).filter(title == SubscribeTvs.NAME, str(year) == SubscribeTvs.YEAR).count()
                )
            return count > 0

    def insert_rss_tv(
        self,
        media_info: MediaInfo,
        total: int,
        lack: int = 0,
        state: str = "D",
        rss_sites: list | None = None,
        search_sites: list | None = None,
        over_edition: int = 0,
        filter_restype: str | None = None,
        filter_pix: str | None = None,
        filter_team: str | None = None,
        filter_rule: str | None = None,
        filter_include: str | None = None,
        filter_exclude: str | None = None,
        save_path: str | None = None,
        download_setting: int = -1,
        total_ep: str | None = None,
        current_ep: str | None = None,
        fuzzy_match: int = 0,
        desc: str | None = None,
        note: str | None = None,
        keyword: str | None = None,
        rssid: int | None = None,
    ) -> int:
        """
        新增RSS电视剧（rssid 不为空时跳过 is_exists 检查，用于编辑替换场景）
        """
        if search_sites is None:
            search_sites = []
        if rss_sites is None:
            rss_sites = []
        if not media_info:
            return -1
        if not media_info.title:
            return -1
        if fuzzy_match and media_info.begin_season is None:
            season_str = ""
        else:
            season_str = media_info.get_season_string()

        with self.session() as db:
            if not rssid:
                if season_str:
                    count = (
                        db.query(SubscribeTvs)
                        .filter(
                            media_info.title == SubscribeTvs.NAME,
                            str(media_info.year) == SubscribeTvs.YEAR,
                            season_str == SubscribeTvs.SEASON,
                        )
                        .count()
                    )
                else:
                    count = (
                        db.query(SubscribeTvs)
                        .filter(media_info.title == SubscribeTvs.NAME, str(media_info.year) == SubscribeTvs.YEAR)
                        .count()
                    )
                if count > 0:
                    return 9

            db.add(
                SubscribeTvs(
                    NAME=media_info.title,
                    YEAR=media_info.year,
                    SEASON=season_str,
                    TMDBID=media_info.tmdb_id,
                    IMAGE=media_info.get_message_image(),
                    RSS_SITES=JsonUtils.dumps(rss_sites),
                    SEARCH_SITES=JsonUtils.dumps(search_sites),
                    OVER_EDITION=over_edition,
                    FILTER_RESTYPE=filter_restype,
                    FILTER_PIX=filter_pix,
                    FILTER_RULE=filter_rule,
                    FILTER_TEAM=filter_team,
                    FILTER_INCLUDE=filter_include,
                    FILTER_EXCLUDE=filter_exclude,
                    SAVE_PATH=save_path,
                    DOWNLOAD_SETTING=download_setting,
                    FUZZY_MATCH=fuzzy_match,
                    TOTAL_EP=total_ep,
                    CURRENT_EP=current_ep,
                    TOTAL=total,
                    LACK=lack,
                    STATE=state,
                    DESC=desc,
                    NOTE=note,
                    KEYWORD=keyword,
                )
            )
        return 0

    def update_rss_tv(self, rssid: int, **kwargs: str | int | list | None) -> int:
        """
        更新RSS电视剧订阅信息（根据rssid）
        """
        if not rssid:
            return -1
        update_fields = {}
        field_map = {
            "name": "NAME",
            "year": "YEAR",
            "season": "SEASON",
            "tmdbid": "TMDBID",
            "image": "IMAGE",
            "rss_sites": "RSS_SITES",
            "search_sites": "SEARCH_SITES",
            "over_edition": "OVER_EDITION",
            "filter_restype": "FILTER_RESTYPE",
            "filter_pix": "FILTER_PIX",
            "filter_rule": "FILTER_RULE",
            "filter_team": "FILTER_TEAM",
            "filter_include": "FILTER_INCLUDE",
            "filter_exclude": "FILTER_EXCLUDE",
            "save_path": "SAVE_PATH",
            "download_setting": "DOWNLOAD_SETTING",
            "fuzzy_match": "FUZZY_MATCH",
            "total_ep": "TOTAL_EP",
            "current_ep": "CURRENT_EP",
            "total": "TOTAL",
            "lack": "LACK",
            "state": "STATE",
            "desc": "DESC",
            "note": "NOTE",
            "keyword": "KEYWORD",
        }
        for k, v in kwargs.items():
            col = field_map.get(k)
            if col is not None:
                if k in ("rss_sites", "search_sites") and isinstance(v, list):
                    update_fields[col] = JsonUtils.dumps(v)
                else:
                    update_fields[col] = v
        if not update_fields:
            return 0
        with self.session() as db:
            db.query(SubscribeTvs).filter(int(rssid) == SubscribeTvs.ID).update(update_fields)
        return 0

    def update_rss_tv_lack(
        self,
        title: str | None = None,
        year: str | None = None,
        season: str | None = None,
        rssid: int | None = None,
        lack_episodes: list | None = None,
    ) -> None:
        """
        更新电视剧缺失的集数
        """
        if not title and not rssid:
            return
        if not lack_episodes:
            lack = 0
            episodes: list[str] = []
        else:
            lack = len(lack_episodes)
            episodes = [str(epi) for epi in lack_episodes]
        with self.session() as db:
            if rssid:
                # 内联 update_rss_tv_episodes，确保与 LACK 更新在同一事务
                if db.query(SubscribeTvEpisodes).filter(int(rssid) == SubscribeTvEpisodes.RSSID).count() > 0:
                    db.query(SubscribeTvEpisodes).filter(int(rssid) == SubscribeTvEpisodes.RSSID).update(
                        {"EPISODES": ",".join(episodes)}
                    )
                else:
                    db.add(SubscribeTvEpisodes(RSSID=rssid, EPISODES=",".join(episodes)))
                db.query(SubscribeTvs).filter(int(rssid) == SubscribeTvs.ID).update({"LACK": lack})
            else:
                db.query(SubscribeTvs).filter(
                    title == SubscribeTvs.NAME, str(year) == SubscribeTvs.YEAR, season == SubscribeTvs.SEASON
                ).update({"LACK": lack})

    def delete_rss_tv(
        self, title: str | None = None, season: str | None = None, rssid: int | None = None, tmdbid: str | None = None
    ) -> None:
        """
        删除RSS电视剧
        """
        if not title and not rssid:
            return
        with self.session() as db:
            if not rssid:
                # 内联 get_rss_tv_id 查找，确保后续删除在同一事务上下文
                if tmdbid:
                    if season:
                        ret = (
                            db.query(SubscribeTvs.ID)
                            .filter(tmdbid == SubscribeTvs.TMDBID, season == SubscribeTvs.SEASON)
                            .first()
                        )
                    else:
                        ret = db.query(SubscribeTvs.ID).filter(tmdbid == SubscribeTvs.TMDBID).first()
                    if ret:
                        rssid = ret[0]
                if not rssid:
                    if season:
                        items = (
                            db.query(SubscribeTvs)
                            .filter(title == SubscribeTvs.NAME, str(season) == SubscribeTvs.SEASON)
                            .all()
                        )
                    else:
                        items = db.query(SubscribeTvs).filter(title == SubscribeTvs.NAME).all()
                    if items:
                        if tmdbid:
                            for item in items:
                                if not item.TMDBID or str(tmdbid) == item.TMDBID:
                                    rssid = item.ID
                                    break
                        else:
                            rssid = items[0].ID
            if rssid:
                # 内联 delete_rss_tv_episodes，确保与 TV 删除在同一事务
                db.query(SubscribeTvEpisodes).filter(int(rssid) == SubscribeTvEpisodes.RSSID).delete()
                db.query(SubscribeTvs).filter(int(rssid) == SubscribeTvs.ID).delete()

    def update_rss_tv_state(
        self,
        title: str | None = None,
        year: str | None = None,
        season: str | None = None,
        rssid: int | None = None,
        state: str = "R",
    ) -> None:
        """
        更新电视剧订阅状态
        """
        if not title and not rssid:
            return
        with self.session() as db:
            if rssid:
                db.query(SubscribeTvs).filter(int(rssid) == SubscribeTvs.ID).update({"STATE": state})
            else:
                db.query(SubscribeTvs).filter(
                    title == SubscribeTvs.NAME, str(year) == SubscribeTvs.YEAR, season == SubscribeTvs.SEASON
                ).update({"STATE": state})

    # ==================== RSS TV Episodes ====================

    def is_exists_rss_tv_episodes(self, rid: int | None) -> bool:
        """
        判断RSS电视剧剧集是否存在
        """
        if not rid:
            return False
        with self.session() as db:
            count = db.query(SubscribeTvEpisodes).filter(int(rid) == SubscribeTvEpisodes.RSSID).count()
            return count > 0

    def update_rss_tv_episodes(self, rid: int | None, episodes: list | None) -> None:
        """
        插入或更新电视剧订阅缺失剧集
        """
        if not rid:
            return
        if not episodes:
            episodes = []
        else:
            episodes = [str(epi) for epi in episodes]
        with self.session() as db:
            if db.query(SubscribeTvEpisodes).filter(int(rid) == SubscribeTvEpisodes.RSSID).count() > 0:
                db.query(SubscribeTvEpisodes).filter(int(rid) == SubscribeTvEpisodes.RSSID).update(
                    {"EPISODES": ",".join(episodes)}
                )
            else:
                db.add(SubscribeTvEpisodes(RSSID=rid, EPISODES=",".join(episodes)))

    def get_rss_tv_episodes(self, rid: int | None) -> list[int] | None:
        """
        查询电视剧订阅缺失剧集
        """
        if not rid:
            return []
        with self.session() as db:
            ret = db.query(SubscribeTvEpisodes.EPISODES).filter(rid == SubscribeTvEpisodes.RSSID).first()
            if ret:
                return [int(epi) for epi in str(ret[0]).split(",")]
            return None

    def delete_rss_tv_episodes(self, rid: int | None) -> None:
        """
        删除电视剧订阅缺失剧集
        """
        if not rid:
            return
        with self.session() as db:
            db.query(SubscribeTvEpisodes).filter(int(rid) == SubscribeTvEpisodes.RSSID).delete()

    def truncate_rss_episodes(self) -> None:
        """
        清空 RSS 剧集记录（仅清理已完成/失效的订阅关联记录，保护活跃订阅进度）
        """
        with self.session() as db:
            active_ids = {
                row[0] for row in db.query(SubscribeTvs.ID).filter(SubscribeTvs.STATE.in_(["R", "D", "S"])).all()
            }
            query = db.query(SubscribeTvEpisodes)
            if active_ids:
                query = query.filter(~SubscribeTvEpisodes.RSSID.in_(active_ids))
            query.delete(synchronize_session=False)

    # ==================== RSS History ====================

    def get_rss_history(self, rtype: str | None = None, rid: int | None = None) -> list[SubscribeHistory]:
        """
        查询RSS历史
        """
        with self.session() as db:
            if rid:
                return db.query(SubscribeHistory).filter(int(rid) == SubscribeHistory.ID).all()
            if rtype:
                return (
                    db.query(SubscribeHistory)
                    .filter(rtype == SubscribeHistory.TYPE)
                    .order_by(SubscribeHistory.FINISH_TIME.desc())
                    .all()
                )
            return db.query(SubscribeHistory).order_by(SubscribeHistory.FINISH_TIME.desc()).all()

    def is_exists_rss_history(self, rssid: int | None) -> bool:
        """
        判断RSS历史是否存在
        """
        if not rssid:
            return False
        with self.session() as db:
            count = db.query(SubscribeHistory).filter(rssid == SubscribeHistory.RSSID).count()
            return count > 0

    def check_rss_history(self, type_str: str, name: str, year: str, season: str) -> bool:
        """
        检查RSS历史是否存在
        """
        with self.session() as db:
            count = (
                db.query(SubscribeHistory)
                .filter(
                    type_str == SubscribeHistory.TYPE,
                    name == SubscribeHistory.NAME,
                    year == SubscribeHistory.YEAR,
                    season == SubscribeHistory.SEASON,
                )
                .count()
            )
            return count > 0

    def insert_rss_history(
        self,
        rssid: int,
        rtype: str,
        name: str,
        year: str,
        tmdbid: str,
        image: str,
        desc: str,
        season: str | None = None,
        total: str | None = None,
        start: str | None = None,
    ) -> None:
        """
        登记RSS历史
        """
        with self.session() as db:
            if db.query(SubscribeHistory).filter(rssid == SubscribeHistory.RSSID).count() > 0:
                return
            db.add(
                SubscribeHistory(
                    TYPE=rtype,
                    RSSID=rssid,
                    NAME=name,
                    YEAR=year,
                    TMDBID=tmdbid,
                    SEASON=season,
                    IMAGE=image,
                    DESC=desc,
                    TOTAL=total,
                    START=start,
                    FINISH_TIME=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time())),
                )
            )

    def delete_rss_history(self, rssid: int | None) -> None:
        """
        删除RSS历史
        """
        if not rssid:
            return
        with self.session() as db:
            db.query(SubscribeHistory).filter(int(rssid) == SubscribeHistory.ID).delete()

    # ==================== RSS Torrents ====================

    def get_rss_torrent_by_enclosure(self, enclosure: str) -> SubscribeTorrents | None:
        """根据 enclosure 获取 RSS 种子记录"""
        if not enclosure:
            return None
        with self.session() as db:
            return db.query(SubscribeTorrents).filter(enclosure == SubscribeTorrents.ENCLOSURE).first()

    def get_rss_torrent_by_name(self, torrent_name: str) -> SubscribeTorrents | None:
        """根据 torrent_name 获取 RSS 种子记录"""
        if not torrent_name:
            return None
        with self.session() as db:
            return db.query(SubscribeTorrents).filter(torrent_name == SubscribeTorrents.TORRENT_NAME).first()

    def insert_rss_torrent(
        self, torrent_name: str, enclosure: str, type_: str, title: str, year: str, season: str, episode: str
    ) -> None:
        """插入 RSS 种子记录"""
        if enclosure and enclosure.startswith("magnet:"):
            enclosure = enclosure.split("&")[0]
        elif enclosure and len(enclosure) > 4000:
            enclosure = enclosure[:4000]
        with self.session() as db:
            db.add(
                SubscribeTorrents(
                    TORRENT_NAME=torrent_name,
                    ENCLOSURE=enclosure,
                    TYPE=type_,
                    TITLE=title,
                    YEAR=year,
                    SEASON=season,
                    EPISODE=episode,
                )
            )

    def simple_insert_rss_torrent(self, title: str, enclosure: str) -> None:
        """简式插入 RSS 种子记录"""
        if enclosure and enclosure.startswith("magnet:"):
            enclosure = enclosure.split("&")[0]
        elif enclosure and len(enclosure) > 4000:
            enclosure = enclosure[:4000]
        with self.session() as db:
            db.add(
                SubscribeTorrents(
                    TORRENT_NAME=title,
                    ENCLOSURE=enclosure,
                )
            )

    def simple_delete_rss_torrent(self, title: str, enclosure: str | None = None) -> None:
        """删除 RSS 种子记录"""
        with self.session() as db:
            if enclosure:
                db.query(SubscribeTorrents).filter(
                    title == SubscribeTorrents.TORRENT_NAME,
                    enclosure == SubscribeTorrents.ENCLOSURE,
                ).delete()
            else:
                db.query(SubscribeTorrents).filter(title == SubscribeTorrents.TORRENT_NAME).delete()

    def truncate_rss_torrents(self) -> None:
        """清空 RSS 种子记录"""
        with self.session() as db:
            db.query(SubscribeTorrents).delete()

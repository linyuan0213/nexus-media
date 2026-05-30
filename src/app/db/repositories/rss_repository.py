"""
RSS Repository
Handles RSS movies, TV shows, episodes and history related database operations.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from app.db.transaction import auto_commit
from app.db.models import RSSHISTORY, RSSMOVIES, RSSTORRENTS, RSSTVEPISODES, RSSTVS
from app.db.repositories.base_repository import BaseRepository
from app.utils.types import MediaType

if TYPE_CHECKING:
    from app.media.models import MediaInfo


class RssRepository(BaseRepository):
    """
    RSS订阅仓储
    处理RSS电影、电视剧、剧集和历史记录的数据库操作
    """

    @auto_commit(BaseRepository._db)
    def reset_rss_state(self) -> None:
        """
        初始化时批量重置所有 RSS 订阅状态
        将 STATE='S' 的订阅重置为 STATE='R'
        """
        self._db.query(RSSMOVIES).filter(RSSMOVIES.STATE == "S").update({"STATE": "R"}, synchronize_session=False)
        self._db.query(RSSTVS).filter(RSSTVS.STATE == "S").update({"STATE": "R"}, synchronize_session=False)

    # ==================== RSS Movies ====================

    def get_rss_movies(self, state: str | None = None, rssid: int | None = None) -> list[RSSMOVIES]:
        """
        查询订阅电影信息
        """
        if rssid:
            return self._db.query(RSSMOVIES).filter(int(rssid) == RSSMOVIES.ID).all()
        else:
            if not state:
                return self._db.query(RSSMOVIES).all()
            else:
                return self._db.query(RSSMOVIES).filter(state == RSSMOVIES.STATE).all()

    def get_rss_movie_id(self, title: str, year: str | None = None, tmdbid: str | None = None) -> int | str | None:
        """
        获取订阅电影ID
        """
        if not title:
            return None
        if tmdbid:
            ret = self._db.query(RSSMOVIES.ID).filter(str(tmdbid) == RSSMOVIES.TMDBID).first()
            if ret:
                return ret[0]
        if not year:
            items = self._db.query(RSSMOVIES).filter(title == RSSMOVIES.NAME).all()
        else:
            items = self._db.query(RSSMOVIES).filter(title == RSSMOVIES.NAME, str(year) == RSSMOVIES.YEAR).all()
        if items:
            if tmdbid:
                for item in items:
                    if not item.TMDBID or str(tmdbid) == item.TMDBID:
                        return item.ID
            else:
                return items[0].ID
        else:
            return None

    def get_rss_movie_sites(self, rssid: int | None) -> str:
        """
        获取订阅电影站点
        """
        if not rssid:
            return ""
        ret = self._db.query(RSSMOVIES.DESC).filter(int(rssid) == RSSMOVIES.ID).first()
        if ret:
            return ret[0]
        return ""

    @auto_commit(BaseRepository._db)
    def update_rss_movie_tmdb(
        self, rid: int, tmdbid: str, title: str, year: str, image: str, desc: str, note: str
    ) -> None:
        """
        更新订阅电影的部分信息
        """
        if not tmdbid:
            return
        self._db.query(RSSMOVIES).filter(int(rid) == RSSMOVIES.ID).update(
            {
                "TMDBID": tmdbid,
                "NAME": title,
                "YEAR": year,
                "IMAGE": image,
                "NOTE": note,
                "DESC": desc,
            }
        )

    @auto_commit(BaseRepository._db)
    def update_rss_movie_desc(self, rid: int, desc: str) -> None:
        """
        更新订阅电影的DESC
        """
        self._db.query(RSSMOVIES).filter(int(rid) == RSSMOVIES.ID).update({"DESC": desc})

    @auto_commit(BaseRepository._db)
    def update_rss_filter_order(self, rtype: str, rssid: int, res_order: str) -> None:
        """
        更新订阅命中的过滤规则优先级
        """
        if rtype == MediaType.MOVIE:
            self._db.query(RSSMOVIES).filter(int(rssid) == RSSMOVIES.ID).update({"FILTER_ORDER": res_order})
        else:
            self._db.query(RSSTVS).filter(int(rssid) == RSSTVS.ID).update({"FILTER_ORDER": res_order})

    def get_rss_overedition_order(self, rtype: str, rssid: int) -> int:
        """
        查询当前订阅的过滤优先级
        """
        if rtype == MediaType.MOVIE:
            res = self._db.query(RSSMOVIES.FILTER_ORDER).filter(int(rssid) == RSSMOVIES.ID).first()
        else:
            res = self._db.query(RSSTVS.FILTER_ORDER).filter(int(rssid) == RSSTVS.ID).first()
        if res and res[0]:
            return int(res[0])
        else:
            return 0

    def is_exists_rss_movie(self, title: str, year: str | None = None) -> bool:
        """
        判断RSS电影是否存在
        """
        if not title:
            return False
        if year is not None:
            count = self._db.query(RSSMOVIES).filter(title == RSSMOVIES.NAME, str(year) == RSSMOVIES.YEAR).count()
        else:
            count = self._db.query(RSSMOVIES).filter(title == RSSMOVIES.NAME).count()
        return count > 0

    @auto_commit(BaseRepository._db)
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
        if self.is_exists_rss_movie(media_info.title, media_info.year):
            return 9

        self._db.insert(
            RSSMOVIES(
                NAME=media_info.title,
                YEAR=media_info.year,
                TMDBID=media_info.tmdb_id,
                IMAGE=media_info.get_message_image(),
                RSS_SITES=json.dumps(rss_sites),
                SEARCH_SITES=json.dumps(search_sites),
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

    @auto_commit(BaseRepository._db)
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
                    update_fields[col] = json.dumps(v)
                else:
                    update_fields[col] = v
        if update_fields:
            self._db.query(RSSMOVIES).filter(int(rssid) == RSSMOVIES.ID).update(update_fields)
        return 0

    @auto_commit(BaseRepository._db)
    def delete_rss_movie(
        self, title: str | None = None, year: str | None = None, rssid: int | None = None, tmdbid: str | None = None
    ) -> None:
        """
        删除RSS电影
        """
        if not title and not rssid:
            return
        if rssid:
            self._db.query(RSSMOVIES).filter(int(rssid) == RSSMOVIES.ID).delete()
        else:
            if tmdbid:
                self._db.query(RSSMOVIES).filter(tmdbid == RSSMOVIES.TMDBID).delete()
            self._db.query(RSSMOVIES).filter(title == RSSMOVIES.NAME, str(year) == RSSMOVIES.YEAR).delete()

    @auto_commit(BaseRepository._db)
    def update_rss_movie_state(
        self, title: str | None = None, year: str | None = None, rssid: int | None = None, state: str = "R"
    ) -> None:
        """
        更新电影订阅状态
        """
        if not title and not rssid:
            return
        if rssid:
            self._db.query(RSSMOVIES).filter(int(rssid) == RSSMOVIES.ID).update({"STATE": state})
        else:
            self._db.query(RSSMOVIES).filter(title == RSSMOVIES.NAME, str(year) == RSSMOVIES.YEAR).update(
                {"STATE": state}
            )

    # ==================== RSS TV Shows ====================

    def get_rss_tvs(self, state: str | None = None, rssid: int | None = None) -> list[RSSTVS]:
        """
        查询订阅电视剧信息
        """
        if rssid:
            return self._db.query(RSSTVS).filter(int(rssid) == RSSTVS.ID).all()
        else:
            if not state:
                return self._db.query(RSSTVS).all()
            else:
                return self._db.query(RSSTVS).filter(state == RSSTVS.STATE).all()

    def get_rss_tv_id(
        self, title: str, year: str | None = None, season: str | None = None, tmdbid: str | None = None
    ) -> int | None:
        """
        获取订阅电视剧ID
        """
        if not title:
            return None
        if tmdbid:
            if season:
                ret = self._db.query(RSSTVS.ID).filter(tmdbid == RSSTVS.TMDBID, season == RSSTVS.SEASON).first()
            else:
                ret = self._db.query(RSSTVS.ID).filter(tmdbid == RSSTVS.TMDBID).first()
            if ret:
                return ret[0]
        if season and year:
            items = (
                self._db.query(RSSTVS)
                .filter(title == RSSTVS.NAME, str(season) == RSSTVS.SEASON, str(year) == RSSTVS.YEAR)
                .all()
            )
        elif season and not year:
            items = self._db.query(RSSTVS).filter(title == RSSTVS.NAME, str(season) == RSSTVS.SEASON).all()
        elif not season and year:
            items = self._db.query(RSSTVS).filter(title == RSSTVS.NAME, str(year) == RSSTVS.YEAR).all()
        else:
            items = self._db.query(RSSTVS).filter(title == RSSTVS.NAME).all()
        if items:
            if tmdbid:
                for item in items:
                    if not item.TMDBID or str(tmdbid) == item.TMDBID:
                        return item.ID
            else:
                return items[0].ID
        else:
            return None

    def get_rss_tv_sites(self, rssid: int | None) -> RSSTVS | str:
        """
        获取订阅电视剧站点
        """
        if not rssid:
            return ""
        ret = self._db.query(RSSTVS).filter(int(rssid) == RSSTVS.ID).first()
        if ret:
            return ret
        return ""

    @auto_commit(BaseRepository._db)
    def update_rss_tv_tmdb(
        self, rid: int, tmdbid: str, title: str, year: str, total: int, lack: int, image: str, desc: str, note: str
    ) -> None:
        """
        更新订阅电视剧的TMDB信息
        """
        if not tmdbid:
            return
        self._db.query(RSSTVS).filter(int(rid) == RSSTVS.ID).update(
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

    @auto_commit(BaseRepository._db)
    def update_rss_tv_desc(self, rid: int, desc: str) -> None:
        """
        更新订阅电视剧的DESC
        """
        self._db.query(RSSTVS).filter(int(rid) == RSSTVS.ID).update({"DESC": desc})

    def is_exists_rss_tv(self, title: str, year: str | None = None, season: str | None = None) -> bool:
        """
        判断RSS电视剧是否存在
        """
        if not title:
            return False
        if season:
            count = (
                self._db.query(RSSTVS)
                .filter(title == RSSTVS.NAME, str(year) == RSSTVS.YEAR, season == RSSTVS.SEASON)
                .count()
            )
        else:
            count = self._db.query(RSSTVS).filter(title == RSSTVS.NAME, str(year) == RSSTVS.YEAR).count()
        return count > 0

    @auto_commit(BaseRepository._db)
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
        if not rssid and self.is_exists_rss_tv(media_info.title, media_info.year, season_str):
            return 9

        self._db.insert(
            RSSTVS(
                NAME=media_info.title,
                YEAR=media_info.year,
                SEASON=season_str,
                TMDBID=media_info.tmdb_id,
                IMAGE=media_info.get_message_image(),
                RSS_SITES=json.dumps(rss_sites),
                SEARCH_SITES=json.dumps(search_sites),
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

    @auto_commit(BaseRepository._db)
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
                    update_fields[col] = json.dumps(v)
                else:
                    update_fields[col] = v
        if update_fields:
            self._db.query(RSSTVS).filter(int(rssid) == RSSTVS.ID).update(update_fields)
        return 0

    @auto_commit(BaseRepository._db)
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
        else:
            lack = len(lack_episodes)
        if rssid:
            self.update_rss_tv_episodes(rssid, lack_episodes)
            self._db.query(RSSTVS).filter(int(rssid) == RSSTVS.ID).update({"LACK": lack})
        else:
            self._db.query(RSSTVS).filter(
                title == RSSTVS.NAME, str(year) == RSSTVS.YEAR, season == RSSTVS.SEASON
            ).update({"LACK": lack})

    @auto_commit(BaseRepository._db)
    def delete_rss_tv(
        self, title: str | None = None, season: str | None = None, rssid: int | None = None, tmdbid: str | None = None
    ) -> None:
        """
        删除RSS电视剧
        """
        if not title and not rssid:
            return
        if not rssid:
            rssid = self.get_rss_tv_id(title=title or "", tmdbid=tmdbid, season=season)
        if rssid:
            self.delete_rss_tv_episodes(rssid)
            self._db.query(RSSTVS).filter(int(rssid) == RSSTVS.ID).delete()

    @auto_commit(BaseRepository._db)
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
        if rssid:
            self._db.query(RSSTVS).filter(int(rssid) == RSSTVS.ID).update({"STATE": state})
        else:
            self._db.query(RSSTVS).filter(
                title == RSSTVS.NAME, str(year) == RSSTVS.YEAR, season == RSSTVS.SEASON
            ).update({"STATE": state})

    # ==================== RSS TV Episodes ====================

    def is_exists_rss_tv_episodes(self, rid: int | None) -> bool:
        """
        判断RSS电视剧剧集是否存在
        """
        if not rid:
            return False
        count = self._db.query(RSSTVEPISODES).filter(int(rid) == RSSTVEPISODES.RSSID).count()
        return count > 0

    @auto_commit(BaseRepository._db)
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

        if self.is_exists_rss_tv_episodes(rid):
            self._db.query(RSSTVEPISODES).filter(int(rid) == RSSTVEPISODES.RSSID).update(
                {"EPISODES": ",".join(episodes)}
            )
        else:
            self._db.insert(RSSTVEPISODES(RSSID=rid, EPISODES=",".join(episodes)))

    def get_rss_tv_episodes(self, rid: int | None) -> list[int] | None:
        """
        查询电视剧订阅缺失剧集
        """
        if not rid:
            return []
        ret = self._db.query(RSSTVEPISODES.EPISODES).filter(rid == RSSTVEPISODES.RSSID).first()
        if ret:
            return [int(epi) for epi in str(ret[0]).split(",")]
        else:
            return None

    @auto_commit(BaseRepository._db)
    def delete_rss_tv_episodes(self, rid: int | None) -> None:
        """
        删除电视剧订阅缺失剧集
        """
        if not rid:
            return
        self._db.query(RSSTVEPISODES).filter(int(rid) == RSSTVEPISODES.RSSID).delete()

    @auto_commit(BaseRepository._db)
    def truncate_rss_episodes(self) -> None:
        """
        清空RSS历史记录
        """
        self._db.query(RSSTVEPISODES).delete()

    # ==================== RSS History ====================

    def get_rss_history(self, rtype: str | None = None, rid: int | None = None) -> list[RSSHISTORY]:
        """
        查询RSS历史
        """
        if rid:
            return self._db.query(RSSHISTORY).filter(int(rid) == RSSHISTORY.ID).all()
        elif rtype:
            return (
                self._db.query(RSSHISTORY)
                .filter(rtype == RSSHISTORY.TYPE)
                .order_by(RSSHISTORY.FINISH_TIME.desc())
                .all()
            )
        return self._db.query(RSSHISTORY).order_by(RSSHISTORY.FINISH_TIME.desc()).all()

    def is_exists_rss_history(self, rssid: int | None) -> bool:
        """
        判断RSS历史是否存在
        """
        if not rssid:
            return False
        count = self._db.query(RSSHISTORY).filter(rssid == RSSHISTORY.RSSID).count()
        return count > 0

    def check_rss_history(self, type_str: str, name: str, year: str, season: str) -> bool:
        """
        检查RSS历史是否存在
        """
        count = (
            self._db.query(RSSHISTORY)
            .filter(
                type_str == RSSHISTORY.TYPE,
                name == RSSHISTORY.NAME,
                year == RSSHISTORY.YEAR,
                season == RSSHISTORY.SEASON,
            )
            .count()
        )
        return count > 0

    @auto_commit(BaseRepository._db)
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
        if not self.is_exists_rss_history(rssid):
            self._db.insert(
                RSSHISTORY(
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

    @auto_commit(BaseRepository._db)
    def delete_rss_history(self, rssid: int | None) -> None:
        """
        删除RSS历史
        """
        if not rssid:
            return
        self._db.query(RSSHISTORY).filter(int(rssid) == RSSHISTORY.ID).delete()

    # ==================== RSS Torrents ====================

    def get_rss_torrent_by_enclosure(self, enclosure: str) -> RSSTORRENTS | None:
        """根据 enclosure 获取 RSS 种子记录"""
        if not enclosure:
            return None
        return self._db.query(RSSTORRENTS).filter(enclosure == RSSTORRENTS.ENCLOSURE).first()

    def get_rss_torrent_by_name(self, torrent_name: str) -> RSSTORRENTS | None:
        """根据 torrent_name 获取 RSS 种子记录"""
        if not torrent_name:
            return None
        return self._db.query(RSSTORRENTS).filter(torrent_name == RSSTORRENTS.TORRENT_NAME).first()

    @auto_commit(BaseRepository._db)
    def insert_rss_torrent(
        self, torrent_name: str, enclosure: str, type_: str, title: str, year: str, season: str, episode: str
    ) -> None:
        """插入 RSS 种子记录"""
        if enclosure and enclosure.startswith("magnet:"):
            enclosure = enclosure.split("&")[0]
        elif enclosure and len(enclosure) > 4000:
            enclosure = enclosure[:4000]
        self._db.insert(
            RSSTORRENTS(
                TORRENT_NAME=torrent_name,
                ENCLOSURE=enclosure,
                TYPE=type_,
                TITLE=title,
                YEAR=year,
                SEASON=season,
                EPISODE=episode,
            )
        )

    @auto_commit(BaseRepository._db)
    def simple_insert_rss_torrent(self, title: str, enclosure: str) -> None:
        """简式插入 RSS 种子记录"""
        if enclosure and enclosure.startswith("magnet:"):
            enclosure = enclosure.split("&")[0]
        elif enclosure and len(enclosure) > 4000:
            enclosure = enclosure[:4000]
        self._db.insert(
            RSSTORRENTS(
                TORRENT_NAME=title,
                ENCLOSURE=enclosure,
            )
        )

    @auto_commit(BaseRepository._db)
    def simple_delete_rss_torrent(self, title: str, enclosure: str | None = None) -> None:
        """删除 RSS 种子记录"""
        if enclosure:
            self._db.query(RSSTORRENTS).filter(
                title == RSSTORRENTS.TORRENT_NAME,
                enclosure == RSSTORRENTS.ENCLOSURE,
            ).delete()
        else:
            self._db.query(RSSTORRENTS).filter(title == RSSTORRENTS.TORRENT_NAME).delete()

    @auto_commit(BaseRepository._db)
    def truncate_rss_torrents(self) -> None:
        """清空 RSS 种子记录"""
        self._db.query(RSSTORRENTS).delete()

"""
RSS Repository
Handles RSS movies, TV shows, episodes and history related database operations.
"""
import json
import time

from sqlalchemy import cast, Integer

from app.db import DbPersist
from app.db.models import RSSMOVIES, RSSTVS, RSSTVEPISODES, RSSHISTORY
from app.db.repositories.base_repository import BaseRepository
from app.utils.types import MediaType


class RssRepository(BaseRepository):
    """
    RSS订阅仓储
    处理RSS电影、电视剧、剧集和历史记录的数据库操作
    """

    # ==================== RSS Movies ====================

    def get_rss_movies(self, state=None, rssid=None):
        """
        查询订阅电影信息
        """
        if rssid:
            return self._db.query(RSSMOVIES).filter(RSSMOVIES.ID == int(rssid)).all()
        else:
            if not state:
                return self._db.query(RSSMOVIES).all()
            else:
                return self._db.query(RSSMOVIES).filter(RSSMOVIES.STATE == state).all()

    def get_rss_movie_id(self, title, year=None, tmdbid=None):
        """
        获取订阅电影ID
        """
        if not title:
            return ""
        if tmdbid:
            ret = self._db.query(RSSMOVIES.ID).filter(RSSMOVIES.TMDBID == str(tmdbid)).first()
            if ret:
                return ret[0]
        if not year:
            items = self._db.query(RSSMOVIES).filter(RSSMOVIES.NAME == title).all()
        else:
            items = self._db.query(RSSMOVIES).filter(RSSMOVIES.NAME == title,
                                                     RSSMOVIES.YEAR == str(year)).all()
        if items:
            if tmdbid:
                for item in items:
                    if not item.TMDBID or item.TMDBID == str(tmdbid):
                        return item.ID
            else:
                return items[0].ID
        else:
            return ""

    def get_rss_movie_sites(self, rssid):
        """
        获取订阅电影站点
        """
        if not rssid:
            return ""
        ret = self._db.query(RSSMOVIES.DESC).filter(RSSMOVIES.ID == int(rssid)).first()
        if ret:
            return ret[0]
        return ""

    @DbPersist(BaseRepository._db)
    def update_rss_movie_tmdb(self, rid, tmdbid, title, year, image, desc, note):
        """
        更新订阅电影的部分信息
        """
        if not tmdbid:
            return
        self._db.query(RSSMOVIES).filter(RSSMOVIES.ID == int(rid)).update({
            "TMDBID": tmdbid,
            "NAME": title,
            "YEAR": year,
            "IMAGE": image,
            "NOTE": note,
            "DESC": desc
        })

    @DbPersist(BaseRepository._db)
    def update_rss_movie_desc(self, rid, desc):
        """
        更新订阅电影的DESC
        """
        self._db.query(RSSMOVIES).filter(RSSMOVIES.ID == int(rid)).update({"DESC": desc})

    @DbPersist(BaseRepository._db)
    def update_rss_filter_order(self, rtype, rssid, res_order):
        """
        更新订阅命中的过滤规则优先级
        """
        if rtype == MediaType.MOVIE:
            self._db.query(RSSMOVIES).filter(RSSMOVIES.ID == int(rssid)).update({
                "FILTER_ORDER": res_order
            })
        else:
            self._db.query(RSSTVS).filter(RSSTVS.ID == int(rssid)).update({
                "FILTER_ORDER": res_order
            })

    def get_rss_overedition_order(self, rtype, rssid):
        """
        查询当前订阅的过滤优先级
        """
        if rtype == MediaType.MOVIE:
            res = self._db.query(RSSMOVIES.FILTER_ORDER).filter(RSSMOVIES.ID == int(rssid)).first()
        else:
            res = self._db.query(RSSTVS.FILTER_ORDER).filter(RSSTVS.ID == int(rssid)).first()
        if res and res[0]:
            return int(res[0])
        else:
            return 0

    def is_exists_rss_movie(self, title, year):
        """
        判断RSS电影是否存在
        """
        if not title:
            return False
        count = self._db.query(RSSMOVIES).filter(RSSMOVIES.NAME == title,
                                                  RSSMOVIES.YEAR == str(year)).count()
        return count > 0

    @DbPersist(BaseRepository._db)
    def insert_rss_movie(self, media_info,
                         state='D',
                         rss_sites=None,
                         search_sites=None,
                         over_edition=0,
                         filter_restype=None,
                         filter_pix=None,
                         filter_team=None,
                         filter_rule=None,
                         filter_include=None,
                         filter_exclude=None,
                         save_path=None,
                         download_setting=-1,
                         fuzzy_match=0,
                         desc=None,
                         note=None,
                         keyword=None):
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

        self._db.insert(RSSMOVIES(
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
            KEYWORD=keyword
        ))
        return 0

    @DbPersist(BaseRepository._db)
    def update_rss_movie(self, rssid, **kwargs):
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
            self._db.query(RSSMOVIES).filter(RSSMOVIES.ID == int(rssid)).update(update_fields)
        return 0

    @DbPersist(BaseRepository._db)
    def delete_rss_movie(self, title=None, year=None, rssid=None, tmdbid=None):
        """
        删除RSS电影
        """
        if not title and not rssid:
            return
        if rssid:
            self._db.query(RSSMOVIES).filter(RSSMOVIES.ID == int(rssid)).delete()
        else:
            if tmdbid:
                self._db.query(RSSMOVIES).filter(RSSMOVIES.TMDBID == tmdbid).delete()
            self._db.query(RSSMOVIES).filter(RSSMOVIES.NAME == title,
                                             RSSMOVIES.YEAR == str(year)).delete()

    @DbPersist(BaseRepository._db)
    def update_rss_movie_state(self, title=None, year=None, rssid=None, state='R'):
        """
        更新电影订阅状态
        """
        if not title and not rssid:
            return
        if rssid:
            self._db.query(RSSMOVIES).filter(RSSMOVIES.ID == int(rssid)).update({"STATE": state})
        else:
            self._db.query(RSSMOVIES).filter(RSSMOVIES.NAME == title,
                                             RSSMOVIES.YEAR == str(year)).update({"STATE": state})

    # ==================== RSS TV Shows ====================

    def get_rss_tvs(self, state=None, rssid=None):
        """
        查询订阅电视剧信息
        """
        if rssid:
            return self._db.query(RSSTVS).filter(RSSTVS.ID == int(rssid)).all()
        else:
            if not state:
                return self._db.query(RSSTVS).all()
            else:
                return self._db.query(RSSTVS).filter(RSSTVS.STATE == state).all()

    def get_rss_tv_id(self, title, year=None, season=None, tmdbid=None):
        """
        获取订阅电视剧ID
        """
        if not title:
            return ""
        if tmdbid:
            if season:
                ret = self._db.query(RSSTVS.ID).filter(RSSTVS.TMDBID == tmdbid,
                                                       RSSTVS.SEASON == season).first()
            else:
                ret = self._db.query(RSSTVS.ID).filter(RSSTVS.TMDBID == tmdbid).first()
            if ret:
                return ret[0]
        if season and year:
            items = self._db.query(RSSTVS).filter(RSSTVS.NAME == title,
                                                  RSSTVS.SEASON == str(season),
                                                  RSSTVS.YEAR == str(year)).all()
        elif season and not year:
            items = self._db.query(RSSTVS).filter(RSSTVS.NAME == title,
                                                  RSSTVS.SEASON == str(season)).all()
        elif not season and year:
            items = self._db.query(RSSTVS).filter(RSSTVS.NAME == title,
                                                  RSSTVS.YEAR == str(year)).all()
        else:
            items = self._db.query(RSSTVS).filter(RSSTVS.NAME == title).all()
        if items:
            if tmdbid:
                for item in items:
                    if not item.TMDBID or item.TMDBID == str(tmdbid):
                        return item.ID
            else:
                return items[0].ID
        else:
            return ""

    def get_rss_tv_sites(self, rssid):
        """
        获取订阅电视剧站点
        """
        if not rssid:
            return ""
        ret = self._db.query(RSSTVS).filter(RSSTVS.ID == int(rssid)).first()
        if ret:
            return ret
        return ""

    @DbPersist(BaseRepository._db)
    def update_rss_tv_tmdb(self, rid, tmdbid, title, year, total, lack, image, desc, note):
        """
        更新订阅电视剧的TMDB信息
        """
        if not tmdbid:
            return
        self._db.query(RSSTVS).filter(RSSTVS.ID == int(rid)).update({
            "TMDBID": tmdbid,
            "NAME": title,
            "YEAR": year,
            "TOTAL": total,
            "LACK": lack,
            "IMAGE": image,
            "DESC": desc,
            "NOTE": note
        })

    @DbPersist(BaseRepository._db)
    def update_rss_tv_desc(self, rid, desc):
        """
        更新订阅电视剧的DESC
        """
        self._db.query(RSSTVS).filter(RSSTVS.ID == int(rid)).update({"DESC": desc})

    def is_exists_rss_tv(self, title, year, season=None):
        """
        判断RSS电视剧是否存在
        """
        if not title:
            return False
        if season:
            count = self._db.query(RSSTVS).filter(RSSTVS.NAME == title,
                                                  RSSTVS.YEAR == str(year),
                                                  RSSTVS.SEASON == season).count()
        else:
            count = self._db.query(RSSTVS).filter(RSSTVS.NAME == title,
                                                  RSSTVS.YEAR == str(year)).count()
        return count > 0

    @DbPersist(BaseRepository._db)
    def insert_rss_tv(self,
                      media_info,
                      total,
                      lack=0,
                      state="D",
                      rss_sites=None,
                      search_sites=None,
                      over_edition=0,
                      filter_restype=None,
                      filter_pix=None,
                      filter_team=None,
                      filter_rule=None,
                      filter_include=None,
                      filter_exclude=None,
                      save_path=None,
                      download_setting=-1,
                      total_ep=None,
                      current_ep=None,
                      fuzzy_match=0,
                      desc=None,
                      note=None,
                      keyword=None,
                      rssid=None):
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

        self._db.insert(RSSTVS(
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
            KEYWORD=keyword
        ))
        return 0

    @DbPersist(BaseRepository._db)
    def update_rss_tv(self, rssid, **kwargs):
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
            self._db.query(RSSTVS).filter(RSSTVS.ID == int(rssid)).update(update_fields)
        return 0

    @DbPersist(BaseRepository._db)
    def update_rss_tv_lack(self, title=None, year=None, season=None, rssid=None, lack_episodes: list = None):
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
            self._db.query(RSSTVS).filter(RSSTVS.ID == int(rssid)).update({"LACK": lack})
        else:
            self._db.query(RSSTVS).filter(RSSTVS.NAME == title,
                                          RSSTVS.YEAR == str(year),
                                          RSSTVS.SEASON == season).update({"LACK": lack})

    @DbPersist(BaseRepository._db)
    def delete_rss_tv(self, title=None, season=None, rssid=None, tmdbid=None):
        """
        删除RSS电视剧
        """
        if not title and not rssid:
            return
        if not rssid:
            rssid = self.get_rss_tv_id(title=title, tmdbid=tmdbid, season=season)
        if rssid:
            self.delete_rss_tv_episodes(rssid)
            self._db.query(RSSTVS).filter(RSSTVS.ID == int(rssid)).delete()

    @DbPersist(BaseRepository._db)
    def update_rss_tv_state(self, title=None, year=None, season=None, rssid=None, state='R'):
        """
        更新电视剧订阅状态
        """
        if not title and not rssid:
            return
        if rssid:
            self._db.query(RSSTVS).filter(RSSTVS.ID == int(rssid)).update({"STATE": state})
        else:
            self._db.query(RSSTVS).filter(RSSTVS.NAME == title,
                                          RSSTVS.YEAR == str(year),
                                          RSSTVS.SEASON == season).update({"STATE": state})

    # ==================== RSS TV Episodes ====================

    def is_exists_rss_tv_episodes(self, rid):
        """
        判断RSS电视剧剧集是否存在
        """
        if not rid:
            return False
        count = self._db.query(RSSTVEPISODES).filter(RSSTVEPISODES.RSSID == int(rid)).count()
        return count > 0

    @DbPersist(BaseRepository._db)
    def update_rss_tv_episodes(self, rid, episodes):
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
            self._db.query(RSSTVEPISODES).filter(RSSTVEPISODES.RSSID == int(rid)).update({
                "EPISODES": ",".join(episodes)
            })
        else:
            self._db.insert(RSSTVEPISODES(
                RSSID=rid,
                EPISODES=",".join(episodes)
            ))

    def get_rss_tv_episodes(self, rid):
        """
        查询电视剧订阅缺失剧集
        """
        if not rid:
            return []
        ret = self._db.query(RSSTVEPISODES.EPISODES).filter(RSSTVEPISODES.RSSID == rid).first()
        if ret:
            return [int(epi) for epi in str(ret[0]).split(',')]
        else:
            return None

    @DbPersist(BaseRepository._db)
    def delete_rss_tv_episodes(self, rid):
        """
        删除电视剧订阅缺失剧集
        """
        if not rid:
            return
        self._db.query(RSSTVEPISODES).filter(RSSTVEPISODES.RSSID == int(rid)).delete()

    @DbPersist(BaseRepository._db)
    def truncate_rss_episodes(self):
        """
        清空RSS历史记录
        """
        self._db.query(RSSTVEPISODES).delete()

    # ==================== RSS History ====================

    def get_rss_history(self, rtype=None, rid=None):
        """
        查询RSS历史
        """
        if rid:
            return self._db.query(RSSHISTORY).filter(RSSHISTORY.ID == int(rid)).all()
        elif rtype:
            return self._db.query(RSSHISTORY).filter(RSSHISTORY.TYPE == rtype).order_by(
                RSSHISTORY.FINISH_TIME.desc()).all()
        return self._db.query(RSSHISTORY).order_by(RSSHISTORY.FINISH_TIME.desc()).all()

    def is_exists_rss_history(self, rssid):
        """
        判断RSS历史是否存在
        """
        if not rssid:
            return False
        count = self._db.query(RSSHISTORY).filter(RSSHISTORY.RSSID == rssid).count()
        return count > 0

    def check_rss_history(self, type_str, name, year, season):
        """
        检查RSS历史是否存在
        """
        count = self._db.query(RSSHISTORY).filter(
            RSSHISTORY.TYPE == type_str,
            RSSHISTORY.NAME == name,
            RSSHISTORY.YEAR == year,
            RSSHISTORY.SEASON == season
        ).count()
        return count > 0

    @DbPersist(BaseRepository._db)
    def insert_rss_history(self, rssid, rtype, name, year, tmdbid, image, desc, season=None, total=None, start=None):
        """
        登记RSS历史
        """
        if not self.is_exists_rss_history(rssid):
            self._db.insert(RSSHISTORY(
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
                FINISH_TIME=time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))
            ))

    @DbPersist(BaseRepository._db)
    def delete_rss_history(self, rssid):
        """
        删除RSS历史
        """
        if not rssid:
            return
        self._db.query(RSSHISTORY).filter(RSSHISTORY.ID == int(rssid)).delete()

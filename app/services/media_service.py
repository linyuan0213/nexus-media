# -*- coding: utf-8 -*-
"""
MediaService - 媒体管理业务层
将 web/controllers/media.py 中的复杂业务逻辑下沉到可独立测试的 Service。
"""
import json
import os
import re
from math import floor
from typing import Optional, List, Tuple, Dict, Any

import cn2an
import log
from app.core.system_config import SystemConfig
from app.core.module_config import ModuleConf
from app.services.downloader_core import DownloaderCore as Downloader
from app.services.filetransfer_service import FileTransferService as FileTransfer
from app.helper import ThreadHelper
from app.media import Media, Bangumi, DouBan, Scraper
from app.media.meta import MetaInfo, MetaBase
from app.mediaserver import MediaServer
from app.plugin_framework.event_compat import EventManager
from app.services.search_service import Searcher
from app.services.subscribe_service import SubscribeService as Subscribe
from app.schemas.media import (
    MediaInfoResultDTO,
    SeasonEpisodesResultDTO,
    MediaSearchResultDTO,
    TransferHistoryPageDTO,
    UnknownListPageDTO,
    LibrarySpaceDTO,
)
from app.utils import StringUtils, SystemUtils, ExceptionUtils, TokenCache
from app.utils.types import MediaType, MovieTypes, EventType, SystemConfigKey
from app.helper.image_proxy_helper import ImageProxyHelper
from config import Config
from app.utils.path_utils import get_category_path
from app.utils.web_utils import WebUtils


class MediaInfoService:
    """
    媒体信息查询业务服务
    负责 TMDB/豆瓣 媒体信息查询、订阅信息回退、季列表等
    """

    def __init__(self,
                 media: Optional[Media] = None,
                 subscribe: Optional[Subscribe] = None,
                 media_server: Optional[MediaServer] = None):
        self._media = media or Media()
        self._subscribe = subscribe or Subscribe()
        self._media_server = media_server or MediaServer()

    def _get_media_exists_info(self, mtype, title, year, mediaid=None):
        """判断媒体是否存在并返回相关信息（使用服务层依赖）"""
        if not mtype or not title:
            return False, None, ""
        if not str(mtype).upper() == "MOV":
            title = "%s (%s)" % (title, year) if year else title
        # 豆瓣/BGM ID 格式无法直接匹配订阅表的 tmdbid，传 None 让 subscribe 用 title+year 匹配
        subscribe_mediaid = mediaid
        if mediaid and (str(mediaid).startswith("DB:") or str(mediaid).startswith("BGM:")):
            subscribe_mediaid = None
        favor = self._media_server.check_item_exists(
            mtype=mtype, title=title, year=year, tmdbid=mediaid)
        rssid = self._subscribe.get_subscribe_id(
            mtype=MediaType.MOVIE if str(mtype).upper() == "MOV" else MediaType.TV,
            title=title, year=year, tmdbid=subscribe_mediaid)
        if not rssid:
            rssid = self._subscribe.get_subscribe_id(
                mtype=MediaType.MOVIE if str(mtype).upper() == "MOV" else MediaType.TV,
                title=title, year=year, tmdbid=None)
        if not rssid:
            # 年份可能不一致（如豆瓣 2025 vs 订阅 2026），尝试忽略年份仅按标题匹配
            rssid = self._subscribe.get_subscribe_id(
                mtype=MediaType.MOVIE if str(mtype).upper() == "MOV" else MediaType.TV,
                title=title, year=None, tmdbid=None)
        if rssid:
            if str(rssid).find('\n') != -1:
                _, rssid = str(rssid).split("\n")
        else:
            rssid = ""
        # fav 语义："2"=已入库, "1"=已订阅, ""=无
        fav = "2" if favor else ("1" if rssid else "")
        return fav, rssid, ""

    def get_season_episodes(self, tmdbid, title, year, season) -> SeasonEpisodesResultDTO:
        """查询 TMDB 剧集情况并检查媒体服务器存在状态"""
        episodes = self._media.get_tmdb_season_episodes(tmdbid=tmdbid, season=season)
        for episode in episodes:
            episode.update({
                "state": True if self._media_server.check_item_exists(
                    mtype=MediaType.TV, title=title, year=year,
                    tmdbid=tmdbid, season=season,
                    episode=episode.get("episode_number")) else False
            })
        return SeasonEpisodesResultDTO(episodes=episodes)

    def get_tvseason_list(self, tmdbid, title) -> List[dict]:
        """获取剧集季列表"""
        if title:
            title_season = MetaInfo(title=title).begin_season
        else:
            title_season = None
        if not str(tmdbid).isdigit():
            media_info = WebUtils.get_mediainfo_from_id(mtype=MediaType.TV, mediaid=tmdbid)
            if not media_info or not media_info.tmdb_info:
                return []
            season_infos = self._media.get_tmdb_tv_seasons(media_info.tmdb_info)
        else:
            season_infos = self._media.get_tmdb_tv_seasons_byid(tmdbid=tmdbid)
        if title_season:
            return [{"text": "第%s季" % title_season, "num": title_season}]
        return [
            {"text": "第%s季" % cn2an.an2cn(season.get("season_number"), mode='low'),
             "num": season.get("season_number")}
            for season in season_infos
        ]

    def get_media_info_detail(self, mediaid, mtype, title, year, page, rssid) -> MediaInfoResultDTO:
        """
        查询媒体信息（优先订阅信息，不足时回退到 TMDB）
        """
        if mtype in MovieTypes:
            media_type = MediaType.MOVIE
        else:
            media_type = MediaType.TV

        rssid_ok = False
        seasons: List[dict] = []
        link_url = ""
        vote_average = 0.0
        poster_path = ""
        release_date = ""
        overview = ""

        if rssid:
            rssid = str(rssid)
            if media_type == MediaType.MOVIE:
                rssinfo = self._subscribe.get_subscribe_movies(rid=rssid)
            else:
                rssinfo = self._subscribe.get_subscribe_tvs(rid=rssid)
            if rssinfo:
                overview = rssinfo[rssid].get("overview") or ""
                poster_path = rssinfo[rssid].get("poster") or ""
                title = rssinfo[rssid].get("name") or ""
                vote_average = rssinfo[rssid].get("vote") or 0.0
                year = rssinfo[rssid].get("year") or ""
                release_date = rssinfo[rssid].get("release_date") or ""
                link_url = self._media.get_detail_url(mtype=media_type,
                                                      tmdbid=rssinfo[rssid].get("tmdbid"))
                if overview and poster_path:
                    rssid_ok = True

        if not rssid_ok:
            if mediaid:
                media = WebUtils.get_mediainfo_from_id(mtype=media_type, mediaid=mediaid)
            else:
                media = self._media.get_media_info(title=f"{title} {year}", mtype=media_type)
            if not media or not media.tmdb_info:
                return MediaInfoResultDTO(type=mtype, type_str=media_type.value,
                                          page=page, title=title or "", year=year or "")
            if not mediaid:
                mediaid = media.tmdb_id
            link_url = media.get_detail_url()
            overview = media.overview or ""
            poster_path = media.get_poster_image() or ""
            title = media.title or ""
            vote_average = round(float(media.vote_average or 0), 1)
            year = media.year or ""
            if media_type != MediaType.MOVIE:
                release_date = media.tmdb_info.get('first_air_date') or ""
                seasons = [{
                    "text": "第%s季" % cn2an.an2cn(season.get("season_number"), mode='low'),
                    "num": season.get("season_number")}
                    for season in self._media.get_tmdb_tv_seasons(tv_info=media.tmdb_info)]
            else:
                release_date = media.tmdb_info.get('release_date') or ""
            if not rssid:
                rssid = self._subscribe.get_subscribe_id(mtype=media_type,
                                                         title=title,
                                                         tmdbid=mediaid)

        if poster_path:
            poster_path = ImageProxyHelper.get_proxy_image_url(
                poster_path, use_proxy=Config().get_config("app").get("enable_image_proxy", True)
            )

        return MediaInfoResultDTO(
            type=mtype, type_str=media_type.value, page=page,
            title=title or "", vote_average=vote_average, poster_path=poster_path,
            release_date=release_date or "", year=year or "", overview=overview or "",
            link_url=link_url, tmdbid=mediaid, rssid=rssid, seasons=seasons or []
        )

    def get_media_person(self, tmdbid, mtype_str, keyword) -> Any:
        """查询演员"""
        mtype = MediaType.MOVIE if mtype_str in MovieTypes else MediaType.TV
        if tmdbid:
            return self._media.get_tmdb_cats(tmdbid=tmdbid, mtype=mtype)
        else:
            return self._media.search_tmdb_person(name=keyword)

    def get_media_recommendations(self, tmdbid, mtype_str, page) -> Any:
        """查询推荐"""
        mtype = MediaType.MOVIE if mtype_str in MovieTypes else MediaType.TV
        if mtype == MediaType.MOVIE:
            return self._media.get_movie_recommendations(tmdbid=tmdbid, page=page)
        else:
            return self._media.get_tv_recommendations(tmdbid=tmdbid, page=page)

    def get_media_similar(self, tmdbid, mtype_str, page) -> Any:
        """查询相似"""
        mtype = MediaType.MOVIE if mtype_str in MovieTypes else MediaType.TV
        if mtype == MediaType.MOVIE:
            return self._media.get_movie_similar(tmdbid=tmdbid, page=page)
        else:
            return self._media.get_tv_similar(tmdbid=tmdbid, page=page)

    def get_person_medias(self, personid, mtype_str, page) -> Any:
        """查询演员参演作品"""
        if mtype_str:
            mtype = MediaType.MOVIE if mtype_str in MovieTypes else MediaType.TV
        else:
            mtype = None
        return self._media.get_person_medias(personid=personid, mtype=mtype, page=page)

    def name_test(self, name, subtitle) -> dict:
        """名称识别测试"""
        from app.utils.web_utils import mediainfo_dict
        media_info = self._media.get_media_info(title=name, subtitle=subtitle)
        if not media_info:
            return {"name": "无法识别"}
        return mediainfo_dict(media_info)

    def search_media_infos(self, keyword, source, page) -> List[dict]:
        """搜索媒体词条"""
        medias = WebUtils.search_media_infos(keyword=keyword, source=source, page=page)
        results = []
        for media in medias:
            d = media.to_dict()
            # 图片 URL 统一走本地代理
            for img_key in ['image', 'poster', 'backdrop']:
                if d.get(img_key):
                    d[img_key] = ImageProxyHelper.get_proxy_image_url(
                        d[img_key], use_proxy=True
                    )
            results.append(d)
        return results

    def get_movie_calendar(self, tid, rssid) -> Optional[dict]:
        """查询电影上映日期"""
        if tid and tid.startswith("DB:"):
            doubanid = tid.replace("DB:", "")
            douban_info = DouBan().get_douban_detail(doubanid=doubanid, mtype=MediaType.MOVIE)
            if not douban_info:
                return None
            poster_path = douban_info.get("cover_url") or ""
            title = douban_info.get("title")
            rating = douban_info.get("rating", {}) or {}
            vote_average = rating.get("value") or "无"
            release_date = douban_info.get("pubdate")
            if release_date:
                release_date = re.sub(r"\(.*\)", "", douban_info.get("pubdate")[0])
            if not release_date:
                return None
            return dict(type="电影", title=title, start=release_date,
                        id=tid, year=release_date[0:4] if release_date else "",
                        poster=poster_path, vote_average=vote_average, rssid=rssid)
        else:
            if tid:
                tmdb_info = self._media.get_tmdb_info(mtype=MediaType.MOVIE, tmdbid=tid)
            else:
                return None
            if not tmdb_info:
                return None
            poster_path = ImageProxyHelper.get_tmdbimage_url(tmdb_info.get('poster_path')) \
                if tmdb_info.get('poster_path') else ""
            title = tmdb_info.get('title')
            vote_average = tmdb_info.get("vote_average")
            release_date = tmdb_info.get('release_date')
            if not release_date:
                return None
            return dict(type="电影", title=title, start=release_date,
                        id=tid, year=release_date[0:4] if release_date else "",
                        poster=poster_path, vote_average=vote_average, rssid=rssid)

    def get_tv_calendar(self, tid, season, name, rssid) -> Optional[list]:
        """查询电视剧上映日期"""
        if tid and tid.startswith("DB:"):
            doubanid = tid.replace("DB:", "")
            douban_info = DouBan().get_douban_detail(doubanid=doubanid, mtype=MediaType.TV)
            if not douban_info:
                return None
            poster_path = douban_info.get("cover_url") or ""
            title = douban_info.get("title")
            rating = douban_info.get("rating", {}) or {}
            vote_average = rating.get("value") or "无"
            release_date = re.sub(r"\(.*\)", "", douban_info.get("pubdate")[0])
            if not release_date:
                return None
            return [{
                "type": "电视剧", "title": title, "start": release_date,
                "id": tid, "year": release_date[0:4] if release_date else "",
                "poster": poster_path, "vote_average": vote_average, "rssid": rssid
            }]
        else:
            if tid:
                tmdb_info = self._media.get_tmdb_tv_season_detail(tmdbid=tid, season=season)
            else:
                return None
            if not tmdb_info:
                return None
            air_date = tmdb_info.get("air_date")
            if not tmdb_info.get("poster_path"):
                tv_tmdb_info = self._media.get_tmdb_info(mtype=MediaType.TV, tmdbid=tid)
                if tv_tmdb_info:
                    poster_path = ImageProxyHelper.get_tmdbimage_url(tv_tmdb_info.get('poster_path'))
                else:
                    poster_path = ""
            else:
                poster_path = ImageProxyHelper.get_tmdbimage_url(tmdb_info.get('poster_path'))
            year = air_date[0:4] if air_date else ""
            events = []
            episodes = tmdb_info.get("episodes") or []
            for episode in episodes:
                if season != 1:
                    title = "%s 第%s季第%s集" % (name, season, episode.get("episode_number"))
                else:
                    title = "%s 第%s集" % (name, episode.get("episode_number"))
                events.append({
                    "type": "剧集", "title": title,
                    "start": episode.get("air_date"),
                    "id": tid, "year": year,
                    "poster": poster_path,
                    "vote_average": episode.get("vote_average") or "无",
                    "rssid": rssid
                })
            return events

    def get_media_detail(self, tmdbid, mtype_str) -> Optional[Dict[str, Any]]:
        """获取媒体详情"""
        mtype = MediaType.MOVIE if mtype_str in MovieTypes else MediaType.TV
        media_info = WebUtils.get_mediainfo_from_id(mtype=mtype, mediaid=tmdbid)
        if not media_info or not media_info.tmdb_info:
            return None
        fav, rssid, item_url = self._get_media_exists_info(
            mtype=mtype, title=media_info.title, year=media_info.year,
            mediaid=media_info.tmdb_id)
        seasons = self._media.get_tmdb_tv_seasons(media_info.tmdb_info)
        if seasons:
            for season in seasons:
                try:
                    exists = self._media_server.check_item_exists(
                        mtype=mtype, title=media_info.title, year=media_info.year,
                        tmdbid=media_info.tmdb_id, season=season.get("season_number"))
                    season.update({"state": True if exists else False})
                except Exception as e:
                    log.error(f"【media_detail】检查季存在状态失败: {str(e)}")
                    season.update({"state": False})
        poster_image = media_info.get_poster_image()
        if poster_image:
            poster_image = ImageProxyHelper.get_proxy_image_url(
                poster_image, use_proxy=Config().get_config("app").get("enable_image_proxy", True)
            )
        return {
            "tmdbid": media_info.tmdb_id,
            "douban_id": media_info.douban_id,
            "background": self._media.get_tmdb_backdrops(tmdbinfo=media_info.tmdb_info),
            "image": poster_image,
            "vote": media_info.vote_average,
            "year": media_info.year,
            "title": media_info.title,
            "genres": self._media.get_tmdb_genres_names(tmdbinfo=media_info.tmdb_info),
            "overview": media_info.overview,
            "runtime": StringUtils.str_timehours(media_info.runtime),
            "fact": self._media.get_tmdb_factinfo(media_info),
            "crews": self._media.get_tmdb_crews(tmdbinfo=media_info.tmdb_info, nums=6),
            "actors": self._media.get_tmdb_cats(mtype=mtype, tmdbid=media_info.tmdb_id),
            "link": media_info.get_detail_url(),
            "douban_link": media_info.get_douban_detail_url(),
            "fav": fav,
            "item_url": item_url,
            "rssid": rssid,
            "seasons": seasons
        }


class MediaRecommendationService:
    """
    媒体推荐/发现业务服务
    """

    def __init__(self,
                 media: Optional[Media] = None,
                 douban: Optional[DouBan] = None,
                 bangumi: Optional[Bangumi] = None,
                 media_server: Optional[MediaServer] = None,
                 subscribe: Optional[Subscribe] = None):
        self._media = media or Media()
        self._douban = douban or DouBan()
        self._bangumi = bangumi or Bangumi()
        self._media_server = media_server or MediaServer()
        self._subscribe = subscribe or Subscribe()

    def _get_media_exists_info(self, mtype, title, year, mediaid=None):
        """判断媒体是否存在并返回相关信息"""
        if not mtype or not title:
            return False, None, ""
        if not str(mtype).upper() == "MOV":
            title = "%s (%s)" % (title, year) if year else title
        # 豆瓣/BGM ID 格式无法直接匹配订阅表的 tmdbid，传 None 让 subscribe 用 title+year 匹配
        subscribe_mediaid = mediaid
        if mediaid and (str(mediaid).startswith("DB:") or str(mediaid).startswith("BGM:")):
            subscribe_mediaid = None
        favor = self._media_server.check_item_exists(
            mtype=mtype, title=title, year=year, tmdbid=mediaid)
        # 订阅查询：先尝试 mediaid（TMDB ID）+ year，再尝试 title+year，最后 title only（处理年份差异）
        rssid = self._subscribe.get_subscribe_id(
            mtype=MediaType.MOVIE if str(mtype).upper() == "MOV" else MediaType.TV,
            title=title, year=year, tmdbid=subscribe_mediaid)
        if not rssid:
            rssid = self._subscribe.get_subscribe_id(
                mtype=MediaType.MOVIE if str(mtype).upper() == "MOV" else MediaType.TV,
                title=title, year=year, tmdbid=None)
        if not rssid:
            # 年份可能不一致（如豆瓣 2025 vs 订阅 2026），尝试忽略年份仅按标题匹配
            rssid = self._subscribe.get_subscribe_id(
                mtype=MediaType.MOVIE if str(mtype).upper() == "MOV" else MediaType.TV,
                title=title, year=None, tmdbid=None)
        if rssid:
            if str(rssid).find('\n') != -1:
                _, rssid = str(rssid).split("\n")
        else:
            rssid = ""
        # fav 语义："2"=已入库, "1"=已订阅, ""=无
        fav = "2" if favor else ("1" if rssid else "")
        return fav, rssid, ""

    def get_recommend_items(self, data: dict) -> List[dict]:
        """
        根据 type/subtype 获取推荐列表
        """
        Type = data.get("type")
        SubType = data.get("subtype")
        CurrentPage = int(data.get("page", 1))
        res_list = []

        if Type in ['MOV', 'TV', 'ALL']:
            if SubType == "hm":
                res_list = self._media.get_tmdb_hot_movies(CurrentPage)
            elif SubType == "ht":
                res_list = self._media.get_tmdb_hot_tvs(CurrentPage)
            elif SubType == "nm":
                res_list = self._media.get_tmdb_new_movies(CurrentPage)
            elif SubType == "nt":
                res_list = self._media.get_tmdb_new_tvs(CurrentPage)
            elif SubType == "dbom":
                res_list = self._douban.get_douban_online_movie(CurrentPage)
            elif SubType == "dbhm":
                res_list = self._douban.get_douban_hot_movie(CurrentPage)
            elif SubType == "dbht":
                res_list = self._douban.get_douban_hot_tv(CurrentPage)
            elif SubType == "dbdh":
                res_list = self._douban.get_douban_hot_anime(CurrentPage)
            elif SubType == "dbnm":
                res_list = self._douban.get_douban_new_movie(CurrentPage)
            elif SubType == "dbtop":
                res_list = self._douban.get_douban_top250_movie(CurrentPage)
            elif SubType == "dbzy":
                res_list = self._douban.get_douban_hot_show(CurrentPage)
            elif SubType == "dbct":
                res_list = self._douban.get_douban_chinese_weekly_tv(CurrentPage)
            elif SubType == "dbgt":
                res_list = self._douban.get_douban_weekly_tv_global(CurrentPage)
            elif SubType == "bangumi":
                Week = data.get("week")
                res_list = self._bangumi.get_bangumi_calendar(page=CurrentPage, week=Week)
            elif SubType == "sim":
                TmdbId = data.get("tmdbid")
                from app.services.media_service import MediaInfoService
                res_list = MediaInfoService().get_media_similar(
                    tmdbid=TmdbId, mtype_str=Type, page=CurrentPage) or []
            elif SubType == "more":
                TmdbId = data.get("tmdbid")
                from app.services.media_service import MediaInfoService
                res_list = MediaInfoService().get_media_recommendations(
                    tmdbid=TmdbId, mtype_str=Type, page=CurrentPage) or []
            elif SubType == "person":
                PersonId = data.get("personid")
                from app.services.media_service import MediaInfoService
                res_list = MediaInfoService().get_person_medias(
                    personid=PersonId, mtype_str=None if Type == 'ALL' else Type,
                    page=CurrentPage) or []
        elif Type == "SEARCH":
            Keyword = data.get("keyword")
            Source = data.get("source")
            medias = WebUtils.search_media_infos(keyword=Keyword, source=Source, page=CurrentPage)
            res_list = [media.to_dict() for media in medias]
        elif Type == "DOWNLOADED":
            Items = Downloader().get_download_history(page=CurrentPage)
            res_list = self._convert_downloaded(Items)
        elif Type == "TRENDING":
            res_list = self._media.get_tmdb_trending_all_week(page=CurrentPage)
        elif Type == "DISCOVER":
            mtype = MediaType.MOVIE if SubType in MovieTypes else MediaType.TV
            params = data.get("params") or {}
            res_list = self._media.get_tmdb_discover(mtype=mtype, page=CurrentPage, params=params)
        elif Type == "DOUBANTAG":
            mtype = MediaType.MOVIE if SubType in MovieTypes else MediaType.TV
            params = data.get("params") or {}
            sort = params.get("sort") or "R"
            tags = params.get("tags") or ""
            res_list = self._douban.get_douban_disover(mtype=mtype, sort=sort,
                                                       tags=tags, page=CurrentPage)

        # 补充存在与订阅状态
        for res in res_list:
            fav, rssid, _ = self._get_media_exists_info(
                mtype=res.get("type"), title=res.get("title"),
                year=res.get("year"), mediaid=res.get("id"))
            res.update({'fav': fav, 'rssid': rssid})

        # 统一转换图片URL为本地代理路径
        try:
            from app.helper.image_proxy_helper import ImageProxyHelper
            for res in res_list:
                if res.get('image'):
                    res['image'] = ImageProxyHelper.get_proxy_image_url(res['image'], use_proxy=True)
        except Exception:
            pass

        return res_list

    @staticmethod
    def _convert_downloaded(Items) -> List[dict]:
        if not Items:
            return []
        return [{
            'id': item.TMDBID,
            'orgid': item.TMDBID,
            'tmdbid': item.TMDBID,
            'title': item.TITLE,
            'type': 'MOV' if item.TYPE == "电影" else "TV",
            'media_type': item.TYPE,
            'year': item.YEAR,
            'vote': item.VOTE,
            'image': item.POSTER,
            'overview': item.TORRENT,
            "date": item.DATE,
            "site": item.SITE
        } for item in Items]


class SearchResultService:
    """
    搜索结果分组业务服务
    """

    def __init__(self,
                 media_server: Optional[MediaServer] = None,
                 subscribe: Optional[Subscribe] = None):
        self._media_server = media_server or MediaServer()
        self._subscribe = subscribe or Subscribe()

    def _get_media_exists_info(self, mtype, title, year, mediaid=None):
        """判断媒体是否存在并返回相关信息"""
        if not mtype or not title:
            return False, None, ""
        if not str(mtype).upper() == "MOV":
            title = "%s (%s)" % (title, year) if year else title
        subscribe_mediaid = mediaid
        if mediaid and (str(mediaid).startswith("DB:") or str(mediaid).startswith("BGM:")):
            subscribe_mediaid = None
        favor = self._media_server.check_item_exists(
            mtype=mtype, title=title, year=year, tmdbid=mediaid)
        rssid = self._subscribe.get_subscribe_id(
            mtype=MediaType.MOVIE if str(mtype).upper() == "MOV" else MediaType.TV,
            title=title, year=year, tmdbid=subscribe_mediaid)
        if not rssid:
            rssid = self._subscribe.get_subscribe_id(
                mtype=MediaType.MOVIE if str(mtype).upper() == "MOV" else MediaType.TV,
                title=title, year=year, tmdbid=None)
        if not rssid:
            # 年份可能不一致（如豆瓣 2025 vs 订阅 2026），尝试忽略年份仅按标题匹配
            rssid = self._subscribe.get_subscribe_id(
                mtype=MediaType.MOVIE if str(mtype).upper() == "MOV" else MediaType.TV,
                title=title, year=None, tmdbid=None)
        if rssid:
            if str(rssid).find('\n') != -1:
                _, rssid = str(rssid).split("\n")
        else:
            rssid = ""
        # fav 语义："2"=已入库, "1"=已订阅, ""=无
        fav = "2" if favor else ("1" if rssid else "")
        return fav, rssid, ""

    def group_search_results(self, search_results: list) -> MediaSearchResultDTO:
        """
        对搜索结果按标题、季集、分辨率等维度分组
        """
        SearchResults = {}
        total = len(search_results)

        for item in search_results:
            restype, respix, reseffect, video_encode = self._parse_res_type(item.RES_TYPE)
            group_key = re.sub(r"[-.\s@|]", "", f"{respix}_{restype}").lower()
            group_info = {"respix": respix, "restype": restype}
            unique_key = re.sub(r"[-.\s@|]", "",
                                f"{respix}_{restype}_{video_encode}_{reseffect}_{item.SIZE}_{item.OTHERINFO}").lower()
            unique_info = {
                "video_encode": video_encode,
                "size": StringUtils.str_filesize(item.SIZE),
                "reseffect": reseffect,
                "releasegroup": item.OTHERINFO
            }
            title_string = f"{item.TITLE}"
            if item.YEAR:
                title_string = f"{title_string} ({item.YEAR})"
            mtype = item.TYPE or ""
            SE_key = item.ES_STRING if item.ES_STRING and mtype != "MOV" else "MOV"
            media_type = {"MOV": "电影", "TV": "电视剧", "ANI": "动漫"}.get(mtype)
            labels = [label for label in str(item.NOTE).split("|")
                      if label in ["官方", "官组", "中字", "国语", "粤语", "国配", "特效", "特效字幕"]]
            torrent_item = {
                "id": item.ID, "seeders": item.SEEDERS,
                "enclosure": item.ENCLOSURE, "site": item.SITE,
                "torrent_name": item.TORRENT_NAME,
                "description": item.DESCRIPTION,
                "pageurl": item.PAGEURL,
                "uploadvalue": item.UPLOAD_VOLUME_FACTOR,
                "downloadvalue": item.DOWNLOAD_VOLUME_FACTOR,
                "size": StringUtils.str_filesize(item.SIZE),
                "respix": respix, "restype": restype,
                "reseffect": reseffect, "releasegroup": item.OTHERINFO,
                "video_encode": video_encode, "labels": labels
            }
            free_item = {
                "value": f"{item.UPLOAD_VOLUME_FACTOR} {item.DOWNLOAD_VOLUME_FACTOR}",
                "name": MetaBase.get_free_string(item.UPLOAD_VOLUME_FACTOR, item.DOWNLOAD_VOLUME_FACTOR)
            }
            releasegroup = item.OTHERINFO if item.OTHERINFO is not None else "未知"
            filter_season = SE_key.split()[0] if SE_key and SE_key not in ["MOV", "TV"] else None

            if SearchResults.get(title_string):
                self._merge_into_existing(SearchResults, title_string, SE_key, group_key,
                                          unique_key, torrent_item, group_info, unique_info,
                                          free_item, releasegroup, item.SITE, video_encode,
                                          filter_season)
            else:
                fav, rssid = 0, None
                if item.TMDBID:
                    fav, rssid, _ = self._get_media_exists_info(
                        mtype=mtype, title=item.TITLE, year=item.YEAR, mediaid=item.TMDBID)
                poster_url = item.POSTER
                try:
                    from app.helper.image_proxy_helper import ImageProxyHelper
                    poster_url = ImageProxyHelper.get_proxy_image_url(item.POSTER, use_proxy=True)
                except Exception:
                    pass
                SearchResults[title_string] = {
                    "key": item.ID, "title": item.TITLE, "year": item.YEAR,
                    "type_key": mtype, "image": poster_url, "type": media_type,
                    "vote": item.VOTE, "tmdbid": item.TMDBID, "backdrop": poster_url,
                    "poster": poster_url, "overview": item.OVERVIEW,
                    "fav": fav, "rssid": rssid,
                    "torrent_dict": {
                        SE_key: {
                            group_key: {
                                "group_info": group_info,
                                "group_total": 1,
                                "group_torrents": {
                                    unique_key: {
                                        "unique_info": unique_info,
                                        "torrent_list": [torrent_item]
                                    }
                                }
                            }
                        }
                    },
                    "filter": {
                        "site": [item.SITE],
                        "free": [free_item],
                        "releasegroup": [releasegroup],
                        "video": [video_encode] if video_encode else [],
                        "season": [filter_season] if filter_season else []
                    }
                }

        # 排序
        for title, item in SearchResults.items():
            item["filter"]["season"].sort(reverse=True)
            item["filter"]["releasegroup"] = sorted(
                item["filter"]["releasegroup"], key=lambda x: (x == "未知", x))
            item["torrent_dict"] = sorted(item["torrent_dict"].items(),
                                          key=self._se_sort, reverse=True)
        return MediaSearchResultDTO(total=total, result=SearchResults)

    @staticmethod
    def _parse_res_type(res_type_str):
        """解析资源类型"""
        if res_type_str:
            try:
                res_mix = json.loads(res_type_str)
            except Exception:
                return "", "", "", ""
            return (
                res_mix.get("restype") or "",
                res_mix.get("respix") or "",
                res_mix.get("reseffect") or "",
                res_mix.get("video_encode") or ""
            )
        return "", "", "", ""

    @staticmethod
    def _merge_into_existing(SearchResults, title_string, SE_key, group_key, unique_key,
                             torrent_item, group_info, unique_info, free_item,
                             releasegroup, site, video_encode, filter_season):
        """将新结果合并到已有标题分组中"""
        result_item = SearchResults[title_string]
        torrent_dict = result_item.get("torrent_dict")
        SE_dict = torrent_dict.get(SE_key)
        if SE_dict:
            group = SE_dict.get(group_key)
            if group:
                unique = group.get("group_torrents").get(unique_key)
                if unique:
                    unique["torrent_list"].append(torrent_item)
                    group["group_total"] += 1
                else:
                    group["group_total"] += 1
                    group.get("group_torrents")[unique_key] = {
                        "unique_info": unique_info,
                        "torrent_list": [torrent_item]
                    }
            else:
                SE_dict[group_key] = {
                    "group_info": group_info,
                    "group_total": 1,
                    "group_torrents": {
                        unique_key: {
                            "unique_info": unique_info,
                            "torrent_list": [torrent_item]
                        }
                    }
                }
        else:
            torrent_dict[SE_key] = {
                group_key: {
                    "group_info": group_info,
                    "group_total": 1,
                    "group_torrents": {
                        unique_key: {
                            "unique_info": unique_info,
                            "torrent_list": [torrent_item]
                        }
                    }
                }
            }
        torrent_filter = dict(result_item.get("filter"))
        if free_item not in torrent_filter.get("free"):
            torrent_filter["free"].append(free_item)
        if releasegroup not in torrent_filter.get("releasegroup"):
            torrent_filter["releasegroup"].append(releasegroup)
        if site not in torrent_filter.get("site"):
            torrent_filter["site"].append(site)
        if video_encode and video_encode not in torrent_filter.get("video"):
            torrent_filter["video"].append(video_encode)
        if filter_season and filter_season not in torrent_filter.get("season"):
            torrent_filter["season"].append(filter_season)

    @staticmethod
    def _se_sort(k):
        k = re.sub(r" +|(?<=s\d)\D*?(?=e)|(?<=s\d\d)\D*?(?=e)",
                   " ", k[0], flags=re.I).split()
        return (k[0], k[1]) if len(k) > 1 else ("Z" + k[0], "ZZZ")


class MediaLibraryService:
    """
    媒体库业务服务
    """

    def __init__(self,
                 media_server: Optional[MediaServer] = None,
                 filetransfer: Optional[FileTransfer] = None):
        self._media_server = media_server or MediaServer()
        self._filetransfer = filetransfer or FileTransfer()

    def get_sync_state(self) -> str:
        """获取同步状态文本"""
        status = self._media_server.get_mediasync_status()
        if not status:
            return "未同步"
        return "电影：%s，电视剧：%s，同步时间：%s" % (
            status.get("movie_count"), status.get("tv_count"), status.get("time"))

    def start_sync(self, librarys: list):
        """开始媒体库同步"""
        TokenCache.delete("index")
        SystemConfig().set(key=SystemConfigKey.SyncLibrary, value=librarys)
        ThreadHelper().start_thread(self._media_server.sync_mediaserver, ())

    def get_media_count(self) -> Optional[dict]:
        """获取媒体库统计"""
        media_counts = self._media_server.get_medias_count()
        user_count = self._media_server.get_user_count()
        if media_counts:
            return {
                "Movie": "{:,}".format(media_counts.get('MovieCount')),
                "Series": "{:,}".format(media_counts.get('SeriesCount')),
                "Episodes": "{:,}".format(media_counts.get('EpisodeCount')) if media_counts.get('EpisodeCount') else "",
                "Music": "{:,}".format(media_counts.get('SongCount')),
                "User": user_count
            }
        return None

    def get_play_history(self) -> list:
        """获取播放记录"""
        return self._media_server.get_activity_log(30)

    def init_config(self):
        """初始化媒体服务器配置（代理）"""
        self._media_server.init_config()

    def get_libraries(self):
        """获取媒体库列表（代理）"""
        return self._media_server.get_libraries()

    def get_resume(self, num=12):
        """获取继续观看（代理）"""
        return self._media_server.get_resume(num=num)

    def get_latest(self, num=20):
        """获取最新入库（代理）"""
        return self._media_server.get_latest(num=num)

    def get_space_info(self) -> LibrarySpaceDTO:
        """获取媒体库存储空间"""
        media = Config().get_config('media')
        movie_paths = media.get('movie_path') or []
        if not isinstance(movie_paths, list):
            movie_paths = [movie_paths]
        tv_paths = media.get('tv_path') or []
        if not isinstance(tv_paths, list):
            tv_paths = [tv_paths]
        anime_paths = media.get('anime_path') or []
        if not isinstance(anime_paths, list):
            anime_paths = [anime_paths]

        all_paths = movie_paths + tv_paths + anime_paths
        if not all_paths:
            return LibrarySpaceDTO()

        space_result = SystemUtils.calculate_space_usage(all_paths)
        if not isinstance(space_result, tuple):
            return LibrarySpaceDTO()
        TotalSpace, FreeSpace = space_result
        if not TotalSpace:
            return LibrarySpaceDTO()

        UsedSpace = TotalSpace - FreeSpace
        UsedPercent = "%0.1f" % ((UsedSpace / TotalSpace) * 100)

        def fmt_space(val):
            if val > 1024:
                return "{:,} TB".format(round(val / 1024, 2))
            return "{:,} GB".format(round(val, 2))

        return LibrarySpaceDTO(
            used_percent=UsedPercent,
            free_space=fmt_space(FreeSpace),
            used_space=fmt_space(UsedSpace),
            total_space=fmt_space(TotalSpace)
        )


class TransferHistoryService:
    """
    转移历史业务服务
    """

    def __init__(self, filetransfer: Optional[FileTransfer] = None):
        self._filetransfer = filetransfer or FileTransfer()

    def get_transfer_history_page(self, search_str, page, page_num) -> TransferHistoryPageDTO:
        """分页查询转移历史"""
        if not page_num:
            page_num = 30
        if not page:
            page = 1
        else:
            page = int(page)
        total_count, historys = self._filetransfer.get_transfer_history(search_str, page, page_num)
        historys_list = []
        for history in historys:
            history = history.as_dict()
            sync_mode = history.get("MODE")
            rmt_mode = ModuleConf.get_dictenum_key(ModuleConf.RMT_MODES, sync_mode) if sync_mode else ""
            history.update({"SYNC_MODE": sync_mode, "RMT_MODE": rmt_mode})
            historys_list.append(history)
        total_page = floor(total_count / page_num) + 1
        return TransferHistoryPageDTO(
            total=total_count, result=historys_list, total_page=total_page,
            page_num=page_num, current_page=page
        )

    def get_transfer_statistics(self, days=90) -> dict:
        """获取转移统计"""
        Labels = []
        MovieNums = []
        TvNums = []
        AnimeNums = []
        for statistic in self._filetransfer.get_transfer_statistics(days):
            if not statistic[2]:
                continue
            if statistic[1] not in Labels:
                Labels.append(statistic[1])
            if statistic[0] == "电影":
                MovieNums.append(statistic[2])
                TvNums.append(0)
                AnimeNums.append(0)
            elif statistic[0] == "电视剧":
                TvNums.append(statistic[2])
                MovieNums.append(0)
                AnimeNums.append(0)
            else:
                AnimeNums.append(statistic[2])
                MovieNums.append(0)
                TvNums.append(0)
        return {"Labels": Labels, "MovieNums": MovieNums,
                "TvNums": TvNums, "AnimeNums": AnimeNums}

    def get_unknown_list(self) -> List[dict]:
        """获取未识别记录列表"""
        Items = []
        Records = self._filetransfer.get_transfer_unknown_paths()
        for rec in Records:
            if not rec.PATH:
                continue
            path = rec.PATH.replace("\\", "/") if rec.PATH else ""
            path_to = rec.DEST.replace("\\", "/") if rec.DEST else ""
            sync_mode = rec.MODE or ""
            rmt_mode = ModuleConf.get_dictenum_key(ModuleConf.RMT_MODES, sync_mode) if sync_mode else ""
            Items.append({
                "id": rec.ID, "path": path, "to": path_to, "name": path,
                "sync_mode": sync_mode, "rmt_mode": rmt_mode,
            })
        return Items

    def get_unknown_list_by_page(self, search_str, page, page_num) -> UnknownListPageDTO:
        """分页查询未识别记录"""
        if not page_num:
            page_num = 30
        if not page:
            page = 1
        else:
            page = int(page)
        total_count, Records = self._filetransfer.get_transfer_unknown_paths_by_page(
            search_str, page, page_num)
        Items = []
        for rec in Records:
            if not rec.PATH:
                continue
            path = rec.PATH.replace("\\", "/") if rec.PATH else ""
            path_to = rec.DEST.replace("\\", "/") if rec.DEST else ""
            sync_mode = rec.MODE or ""
            rmt_mode = ModuleConf.get_dictenum_key(ModuleConf.RMT_MODES, sync_mode) if sync_mode else ""
            Items.append({
                "id": rec.ID, "path": path, "to": path_to, "name": path,
                "sync_mode": sync_mode, "rmt_mode": rmt_mode,
            })
        total_page = floor(total_count / page_num) + 1
        return UnknownListPageDTO(
            total=total_count, items=Items, total_page=total_page,
            page_num=page_num, current_page=page
        )

    def re_identify_unknown(self) -> int:
        """重新识别所有未识别记录"""
        from app.services.sync_service import SyncService
        ItemIds = []
        Records = self._filetransfer.get_transfer_unknown_paths()
        for rec in Records:
            if not rec.PATH:
                continue
            ItemIds.append(rec.ID)
        if ItemIds:
            SyncService().re_identify_items(flag="unidentification", ids=ItemIds)
        return len(ItemIds)

    def clear_history(self):
        """清空识别记录"""
        self._filetransfer.delete_transfer()
        self._filetransfer.truncate_transfer_blacklist()


class MediaFileService:
    """
    媒体文件操作业务服务
    """

    def __init__(self):
        pass

    def get_dir_list(self, in_dir: str) -> Tuple[bool, list, str]:
        """获取目录列表"""
        import os
        from app.utils import SystemUtils
        from app.utils.types import OsType

        result = []
        try:
            if not in_dir or in_dir == "/":
                if SystemUtils.get_system() == OsType.WINDOWS:
                    partitions = SystemUtils.get_windows_drives()
                    if partitions:
                        for p in partitions:
                            result.append({"name": p, "path": p, "is_dir": True})
                    else:
                        for f in os.listdir("C:/"):
                            ff = os.path.join("C:/", f)
                            result.append({"name": f, "path": ff.replace("\\", "/"), "is_dir": os.path.isdir(ff)})
                else:
                    for f in os.listdir("/"):
                        ff = os.path.join("/", f)
                        result.append({"name": f, "path": ff.replace("\\", "/"), "is_dir": os.path.isdir(ff)})
            else:
                d = os.path.normpath(in_dir)
                if not os.path.isdir(d):
                    d = os.path.dirname(d)
                for f in os.listdir(d):
                    ff = os.path.join(d, f)
                    is_dir = os.path.isdir(ff)
                    item = {"name": f, "path": ff.replace("\\", "/"), "is_dir": is_dir}
                    try:
                        st = os.stat(ff)
                        item["mtime"] = st.st_mtime
                        item["ctime"] = st.st_ctime
                    except (OSError, IOError):
                        item["mtime"] = None
                        item["ctime"] = None
                    if not is_dir:
                        item["ext"] = os.path.splitext(f)[1][1:]
                        try:
                            item["size"] = os.path.getsize(ff)
                        except (OSError, IOError):
                            item["size"] = None
                    result.append(item)
        except Exception as e:
            return False, [], str(e)
        return True, result, ""

    def get_library_paths(self, media: dict, sync_svc, downloader_svc=None) -> dict:
        """获取媒体库目录 + 同步源目录"""
        import os
        from app.db.models import CONFIGSYNCPATHS

        seen = set()

        def add_path(path: str, label: str, ptype: str):
            if not path:
                return None
            norm = path.replace("\\", "/").rstrip("/")
            if norm in seen:
                return None
            seen.add(norm)
            name = os.path.basename(norm) or label
            return {"name": name, "path": norm, "type": ptype}

        library_paths = []
        movie_paths = media.get('movie_path') or []
        if not isinstance(movie_paths, list):
            movie_paths = [movie_paths] if movie_paths else []
        tv_paths = media.get('tv_path') or []
        if not isinstance(tv_paths, list):
            tv_paths = [tv_paths] if tv_paths else []
        anime_paths = media.get('anime_path') or []
        if not isinstance(anime_paths, list):
            anime_paths = [anime_paths] if anime_paths else []

        for p in movie_paths:
            item = add_path(p, "电影", "movie")
            if item:
                library_paths.append(item)
        for p in tv_paths:
            item = add_path(p, "电视剧", "tv")
            if item:
                library_paths.append(item)
        for p in anime_paths:
            item = add_path(p, "动漫", "anime")
            if item:
                library_paths.append(item)

        sync_source_paths = []
        try:
            sync_confs = sync_svc.get_sync_paths()
            if isinstance(sync_confs, dict):
                for sp in sync_confs.values():
                    src = sp.get("from") if isinstance(sp, dict) else None
                    item = add_path(src, "同步源目录", "sync")
                    if item:
                        sync_source_paths.append(item)
        except Exception:
            pass

        default_path = media.get('media_default_path')
        if not default_path:
            if library_paths:
                default_path = library_paths[0]["path"]
            elif sync_source_paths:
                default_path = sync_source_paths[0]["path"]
            else:
                default_path = os.path.expanduser("~").replace("\\", "/")

        return {
            "library_paths": library_paths,
            "sync_source_paths": sync_source_paths,
            "default_path": default_path,
        }

    def download_subtitle(self, path: str, name: str) -> Tuple[bool, str]:
        """下载字幕"""
        media = Media().get_media_info(title=name)
        if not media or not media.tmdb_info:
            return False, f"{name} 无法从TMDB查询到媒体信息"
        if not media.imdb_id:
            media.set_tmdb_info(Media().get_tmdb_info(mtype=media.type, tmdbid=media.tmdb_id))
        EventManager().send_event(EventType.SubtitleDownload, {
            "media_info": media.to_dict(),
            "file": os.path.splitext(path)[0],
            "file_ext": os.path.splitext(name)[-1],
            "bluray": False
        })
        return True, "字幕下载任务已提交，正在后台运行。"

    def scrap_media_path(self, path: str) -> str:
        """刮削媒体路径"""
        if not path:
            return "请指定刮削路径"
        ThreadHelper().start_thread(Scraper().folder_scraper, (path, None, 'force_all'))
        return "刮削任务已提交，正在后台运行。"

    def get_category_config(self, category_name: str) -> Tuple[bool, str]:
        """获取二级分类配置"""
        if not category_name:
            return False, "请输入二级分类策略名称"
        if category_name == "config":
            return False, "非法二级分类策略名称"
        category_path = os.path.join(Config().config_path, f"{category_name}.yaml")
        if not os.path.exists(category_path):
            return False, "请保存生成配置文件"
        with open(category_path, "r", encoding="utf-8") as f:
            return True, f.read()

    def update_category_config(self, text: str) -> str:
        """保存二级分类配置"""
        category_path = get_category_path()
        if category_path:
            with open(category_path, "w", encoding="utf-8") as f:
                f.write(text)
        return "保存成功"

    def save_user_script(self, script: str, css: str):
        """保存用户自定义脚本"""
        SystemConfig().set(key=SystemConfigKey.CustomScript,
                           value={"css": css, "javascript": script})

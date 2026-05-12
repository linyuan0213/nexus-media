# -*- coding: utf-8 -*-
from typing import Optional, List

from app.media import MediaService, Bangumi, DouBan
from app.mediaserver import MediaServer
from app.services.downloader_core import DownloaderCore as Downloader
from app.services.subscribe_service import SubscribeService as Subscribe
from app.utils.types import MediaType, MovieTypes
from app.utils.media_utils import check_media_exists
from app.utils.web_utils import WebUtils


class MediaRecommendationService:
    """
    媒体推荐/发现业务服务
    """

    def __init__(self,
                 media_service: Optional[MediaService] = None,
                 douban: Optional[DouBan] = None,
                 bangumi: Optional[Bangumi] = None,
                 media_server: Optional[MediaServer] = None,
                 subscribe: Optional[Subscribe] = None):
        self._media = media_service or MediaService()
        self._douban = douban or DouBan()
        self._bangumi = bangumi or Bangumi()
        self._media_server = media_server or MediaServer()
        self._subscribe = subscribe or Subscribe()

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

        for res in res_list:
            fav, rssid, _ = check_media_exists(
                media_server=self._media_server, subscribe=self._subscribe,
                mtype=res.get("type"), title=res.get("title"),
                year=res.get("year"), mediaid=res.get("id"))
            res.update({'fav': fav, 'rssid': rssid})

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

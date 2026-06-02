from app.di import container
from app.helper.image_proxy_helper import ImageProxyHelper
from app.media import Bangumi, DouBan, MediaService
from app.mediaserver import MediaServer
from app.services.subscribe_service import SubscribeService as Subscribe
from app.utils.media_utils import check_media_exists
from app.utils.types import MediaType
from app.utils.web_utils import WebUtils


class MediaRecommendationService:
    """
    媒体推荐/发现业务服务
    """

    def __init__(
        self,
        media_service: MediaService | None = None,
        douban: DouBan | None = None,
        bangumi: Bangumi | None = None,
        media_server: MediaServer | None = None,
        subscribe: Subscribe | None = None,
    ):
        self._media = media_service or container.media_service()
        self._douban = douban or container.douban()
        self._bangumi = bangumi or Bangumi()
        self._media_server = media_server or container.media_server()
        self._subscribe = subscribe or container.subscribe_service()

    def get_recommend_items(self, data: dict) -> list[dict]:
        """
        根据 type/subtype 获取推荐列表
        """
        type_ = data.get("type")
        subtype = data.get("subtype")
        current_page = int(data.get("page", 1))
        res_list = []

        if type_ in [MediaType.MOVIE.value, MediaType.TV.value, "ALL"]:
            if subtype == "hm":
                res_list = self._media.get_tmdb_hot_movies(current_page)
            elif subtype == "ht":
                res_list = self._media.get_tmdb_hot_tvs(current_page)
            elif subtype == "nm":
                res_list = self._media.get_tmdb_new_movies(current_page)
            elif subtype == "nt":
                res_list = self._media.get_tmdb_new_tvs(current_page)
            elif subtype == "dbom":
                res_list = self._douban.get_douban_online_movie(current_page)
            elif subtype == "dbhm":
                res_list = self._douban.get_douban_hot_movie(current_page)
            elif subtype == "dbht":
                res_list = self._douban.get_douban_hot_tv(current_page)
            elif subtype == "dbdh":
                res_list = self._douban.get_douban_hot_anime(current_page)
            elif subtype == "dbnm":
                res_list = self._douban.get_douban_new_movie(current_page)
            elif subtype == "dbtop":
                res_list = self._douban.get_douban_top250_movie(current_page)
            elif subtype == "dbzy":
                res_list = self._douban.get_douban_hot_show(current_page)
            elif subtype == "dbct":
                res_list = self._douban.get_douban_chinese_weekly_tv(current_page)
            elif subtype == "dbgt":
                res_list = self._douban.get_douban_weekly_tv_global(current_page)
            elif subtype == "bangumi":
                week = data.get("week")
                res_list = self._bangumi.get_bangumi_calendar(page=current_page, week=week)
            elif subtype == "sim":
                tmdb_id = data.get("tmdbid")

                res_list = (
                    container.media_info_service().get_media_similar(tmdbid=tmdb_id, mtype_str=type_, page=current_page)
                    or []
                )
            elif subtype == "more":
                tmdb_id = data.get("tmdbid")

                res_list = (
                    container.media_info_service().get_media_recommendations(
                        tmdbid=tmdb_id, mtype_str=type_, page=current_page
                    )
                    or []
                )
            elif subtype == "person":
                person_id = data.get("personid")

                res_list = (
                    container.media_info_service().get_person_medias(
                        personid=person_id, mtype_str=None if type_ == "ALL" else type_, page=current_page
                    )
                    or []
                )
        elif type_ == "SEARCH":
            keyword = data.get("keyword")
            source = data.get("source")
            medias = WebUtils.search_media_infos(keyword=keyword, source=source, page=current_page)
            res_list = [media.to_dict() for media in medias]
        elif type_ == "DOWNLOADED":
            items = container.downloader_core().get_download_history(page=current_page)
            res_list = self._convert_downloaded(items)
        elif type_ == "TRENDING":
            res_list = self._media.get_tmdb_trending_all_week(page=current_page)
        elif type_ == "DISCOVER":
            mtype = MediaType.MOVIE if MediaType.from_string(subtype or "") == MediaType.MOVIE else MediaType.TV
            params = data.get("params") or {}
            res_list = self._media.get_tmdb_discover(mtype=mtype, page=current_page, params=params)
        elif type_ == "DOUBANTAG":
            mtype = MediaType.MOVIE if MediaType.from_string(subtype or "") == MediaType.MOVIE else MediaType.TV
            params = data.get("params") or {}
            sort = params.get("sort") or "R"
            tags = params.get("tags") or ""
            res_list = self._douban.get_douban_disover(mtype=mtype, sort=sort, tags=tags, page=current_page)

        for res in res_list:
            fav, rssid, _ = check_media_exists(
                media_server=self._media_server,
                subscribe=self._subscribe,
                mtype=res.get("type"),
                title=res.get("title"),
                year=res.get("year"),
                mediaid=res.get("id"),
            )
            res.update({"fav": fav, "rssid": rssid})

        try:
            for res in res_list:
                if res.get("image"):
                    res["image"] = ImageProxyHelper.get_proxy_image_url(res["image"], use_proxy=True)
        except Exception:
            pass

        return res_list

    @staticmethod
    def _convert_downloaded(items) -> list[dict]:
        if not items:
            return []
        return [
            {
                "id": item.TMDBID,
                "orgid": item.TMDBID,
                "tmdbid": item.TMDBID,
                "title": item.TITLE,
                "type": MediaType.from_string(item.TYPE).value,
                "media_type": MediaType.from_string(item.TYPE).display_name,
                "year": item.YEAR,
                "vote": item.VOTE,
                "image": item.POSTER,
                "overview": item.TORRENT,
                "date": item.DATE,
                "site": item.SITE,
            }
            for item in items
        ]

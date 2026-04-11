

from app.helper import ThreadHelper
from app.helper import RssHelper
from app.media.meta import MetaInfo
from app.rss import Rss
from app.rsschecker import RssChecker
from app.subscribe import Subscribe
from app.utils.types import MediaType, MovieTypes, RssType
from web.actions._base import WebActionBase


class WebActionRssMixin:
    @staticmethod
    def get_movie_rss_list():
        """
        查询所有电影订阅
        """
        return WebActionBase._success(result=Subscribe().get_subscribe_movies())

    @staticmethod
    def get_tv_rss_list():
        """
        查询所有电视剧订阅
        """
        return WebActionBase._success(result=Subscribe().get_subscribe_tvs())

    @staticmethod
    def get_rss_history(data):
        """
        查询所有订阅历史
        """
        mtype = data.get("type")
        return WebActionBase._success(result=[rec.as_dict() for rec in Rss().get_rss_history(rtype=mtype)])

    @staticmethod
    def get_default_rss_setting(data):
        """
        获取默认订阅设置
        """
        match data.get("mtype"):
            case "TV":
                default_rss_setting = Subscribe().default_rss_setting_tv
            case "MOV":
                default_rss_setting = Subscribe().default_rss_setting_mov
            case _:
                default_rss_setting = {}
        if default_rss_setting:
            return WebActionBase._success(data=default_rss_setting)
        return WebActionBase._fail()

    @staticmethod
    def get_movie_rss_items():
        """
        获取所有电影订阅项目
        """
        RssMovieItems = [
            {
                "id": movie.get("tmdbid"),
                "rssid": movie.get("id")
            } for movie in Subscribe().get_subscribe_movies().values() if movie.get("tmdbid")
        ]
        return WebActionBase._success(result=RssMovieItems)

    @staticmethod
    def get_tv_rss_items():
        """
        获取所有电视剧订阅项目
        """
        # 电视剧订阅
        RssTvItems = [
            {
                "id": tv.get("tmdbid"),
                "rssid": tv.get("id"),
                "season": int(str(tv.get('season')).replace("S", "")),
                "name": tv.get("name"),
            } for tv in Subscribe().get_subscribe_tvs().values() if tv.get('season') and tv.get("tmdbid")
        ]
        # 自定义订阅
        RssTvItems += RssChecker().get_userrss_mediainfos()
        # 电视剧订阅去重
        Uniques = set()
        UniqueTvItems = []
        for item in RssTvItems:
            unique = f"{item.get('id')}_{item.get('season')}"
            if unique not in Uniques:
                Uniques.add(unique)
                UniqueTvItems.append(item)
        return WebActionBase._success(result=UniqueTvItems)

    def get_ical_events(self):
        """
        获取ical日历事件
        """
        Events = []
        # 电影订阅
        RssMovieItems = self.get_movie_rss_items().get("result")
        for movie in RssMovieItems:
            info = self._movie_calendar_data(movie)
            if info.get("id"):
                Events.append(info)

        # 电视剧订阅
        RssTvItems = self.get_tv_rss_items().get("result")
        for tv in RssTvItems:
            infos = self._tv_calendar_data(tv).get("events")
            if infos and isinstance(infos, list):
                for info in infos:
                    if info.get("id"):
                        Events.append(info)

        return self._success(result=Events)

    @staticmethod
    def _remove_rss_media(data):
        """
        移除RSS订阅
        """
        name = data.get("name")
        mtype = data.get("type")
        year = data.get("year")
        season = data.get("season")
        rssid = data.get("rssid")
        page = data.get("page")
        tmdbid = data.get("tmdbid")
        if not str(tmdbid).isdigit():
            tmdbid = None
        if name:
            name = MetaInfo(title=name).get_name()
        if mtype:
            if mtype in MovieTypes:
                Subscribe().delete_subscribe(mtype=MediaType.MOVIE,
                                             title=name,
                                             year=year,
                                             rssid=rssid,
                                             tmdbid=tmdbid)
            else:
                Subscribe().delete_subscribe(mtype=MediaType.TV,
                                             title=name,
                                             season=season,
                                             rssid=rssid,
                                             tmdbid=tmdbid)
        return WebActionBase._success(page=page, name=name)

    @staticmethod
    def _add_rss_media(data):
        """
        添加RSS订阅
        """
        _subscribe = Subscribe()
        channel = RssType.Manual if data.get(
            "in_form") == "manual" else RssType.Auto
        name = data.get("name")
        year = data.get("year")
        keyword = data.get("keyword")
        season = data.get("season")
        fuzzy_match = data.get("fuzzy_match")
        mediaid = data.get("mediaid")
        rss_sites = data.get("rss_sites")
        search_sites = data.get("search_sites")
        over_edition = data.get("over_edition")
        filter_restype = data.get("filter_restype")
        filter_pix = data.get("filter_pix")
        filter_team = data.get("filter_team")
        filter_rule = data.get("filter_rule")
        filter_include = data.get("filter_include")
        filter_exclude = data.get("filter_exclude")
        save_path = data.get("save_path")
        download_setting = data.get("download_setting")
        total_ep = data.get("total_ep")
        current_ep = data.get("current_ep")
        rssid = data.get("rssid")
        page = data.get("page")
        mtype = MediaType.MOVIE if data.get(
            "type") in MovieTypes else MediaType.TV

        media_info = None
        if isinstance(season, list):
            code = 0
            msg = ""
            for sea in season:
                code, msg, media_info = _subscribe.add_rss_subscribe(mtype=mtype,
                                                                     name=name,
                                                                     year=year,
                                                                     channel=channel,
                                                                     keyword=keyword,
                                                                     season=sea,
                                                                     fuzzy_match=fuzzy_match,
                                                                     mediaid=mediaid,
                                                                     rss_sites=rss_sites,
                                                                     search_sites=search_sites,
                                                                     over_edition=over_edition,
                                                                     filter_restype=filter_restype,
                                                                     filter_pix=filter_pix,
                                                                     filter_team=filter_team,
                                                                     filter_rule=filter_rule,
                                                                     filter_include=filter_include,
                                                                     filter_exclude=filter_exclude,
                                                                     save_path=save_path,
                                                                     download_setting=download_setting,
                                                                     rssid=rssid)
                if code != 0:
                    break
        else:
            code, msg, media_info = _subscribe.add_rss_subscribe(mtype=mtype,
                                                                 name=name,
                                                                 year=year,
                                                                 channel=channel,
                                                                 keyword=keyword,
                                                                 season=season,
                                                                 fuzzy_match=fuzzy_match,
                                                                 mediaid=mediaid,
                                                                 rss_sites=rss_sites,
                                                                 search_sites=search_sites,
                                                                 over_edition=over_edition,
                                                                 filter_restype=filter_restype,
                                                                 filter_pix=filter_pix,
                                                                 filter_team=filter_team,
                                                                 filter_rule=filter_rule,
                                                                 filter_include=filter_include,
                                                                 filter_exclude=filter_exclude,
                                                                 save_path=save_path,
                                                                 download_setting=download_setting,
                                                                 total_ep=total_ep,
                                                                 current_ep=current_ep,
                                                                 rssid=rssid)
        if not rssid and media_info:
            rssid = _subscribe.get_subscribe_id(mtype=mtype,
                                                title=name,
                                                tmdbid=media_info.tmdb_id)
        return WebActionBase._fail(code=code, msg=msg, page=page, name=name, rssid=rssid)

    @staticmethod
    def _refresh_rss(data):
        """
        重新搜索RSS
        """
        mtype = data.get("type")
        rssid = data.get("rssid")
        page = data.get("page")
        if mtype == "MOV":
            ThreadHelper().start_thread(Subscribe().subscribe_search_movie, (rssid,))
        else:
            ThreadHelper().start_thread(Subscribe().subscribe_search_tv, (rssid,))
        return WebActionBase._success(page=page)

    @staticmethod
    def _rss_detail(data):
        rid = data.get("rssid")
        mtype = data.get("rsstype")
        if mtype in MovieTypes:
            rssdetail = Subscribe().get_subscribe_movies(rid=rid)
            if not rssdetail:
                return WebActionBase._fail()
            rssdetail = list(rssdetail.values())[0]
            rssdetail["type"] = "MOV"
        else:
            rssdetail = Subscribe().get_subscribe_tvs(rid=rid)
            if not rssdetail:
                return WebActionBase._fail()
            rssdetail = list(rssdetail.values())[0]
            rssdetail["type"] = "TV"
        return WebActionBase._success(detail=rssdetail)

    @staticmethod
    def _delete_rss_history(data):
        rssid = data.get("rssid")
        Rss().delete_rss_history(rssid=rssid)
        return WebActionBase._success()

    @staticmethod
    def _re_rss_history(data):
        rssid = data.get("rssid")
        rtype = data.get("type")
        rssinfo = Rss().get_rss_history(rtype=rtype, rid=rssid)
        if rssinfo:
            if rtype == "MOV":
                mtype = MediaType.MOVIE
            else:
                mtype = MediaType.TV
            if rssinfo[0].SEASON:
                season = int(str(rssinfo[0].SEASON).replace("S", ""))
            else:
                season = None
            code, msg, _ = Subscribe().add_rss_subscribe(mtype=mtype,
                                                         name=rssinfo[0].NAME,
                                                         year=rssinfo[0].YEAR,
                                                         channel=RssType.Auto,
                                                         season=season,
                                                         mediaid=rssinfo[0].TMDBID,
                                                         total_ep=rssinfo[0].TOTAL,
                                                         current_ep=rssinfo[0].START)
            return WebActionBase._fail(code=code, msg=msg)
        else:
            return WebActionBase._fail(msg="订阅历史记录不存在")

    @staticmethod
    def truncate_rsshistory():
        """
        清空RSS历史记录
        """
        RssHelper().truncate_rss_history()
        Subscribe().truncate_rss_episodes()
        return WebActionBase._success()

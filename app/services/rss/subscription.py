"""RSS 订阅业务服务."""

from __future__ import annotations

from typing import Any

from app.helper import RssHelper, ThreadHelper
from app.media import meta_info
from app.schemas.rss import (
    RssAddResultDTO,
    RssDetailResultDTO,
)
from app.services.rss.task_service import RssTaskService
from app.services.rss_core import Rss
from app.services.subscribe_service import SubscribeService as Subscribe
from app.utils.types import MediaType, MovieTypes, RssType


class RssSubscriptionService:
    """
    RSS 订阅业务服务
    负责订阅添加/删除、历史管理、列表查询、日历事件、RSS下载
    """

    def __init__(
        self, subscribe: Subscribe | None = None, rss: Rss | None = None, rss_checker: RssTaskService | None = None
    ):
        self._subscribe: Subscribe = subscribe or Subscribe()
        self._rss: Rss | None = rss
        self._rss_checker: RssTaskService | None = rss_checker

    def download_rss(self) -> None:
        """触发RSS订阅下载"""
        if not self._rss:
            self._rss = Rss()
        self._rss.rssdownload()

    def check_torrent_rss(
        self,
        media_info: Any,
        rss_movies: list[dict],
        rss_tvs: list[dict],
        site_id: int | None,
        site_filter_rule: int | None,
        site_cookie: str | None,
        site_parse: bool,
        site_ua: str | None,
        site_headers: str | dict | None,
        site_proxy: bool,
    ) -> Any:
        """判断种子是否命中订阅（委托给 Rss 模块）"""
        if not self._rss:
            self._rss = Rss()
        return self._rss.check_torrent_rss(
            media_info=media_info,
            rss_movies=rss_movies,
            rss_tvs=rss_tvs,
            site_id=site_id,
            site_filter_rule=site_filter_rule,
            site_cookie=site_cookie,
            site_parse=site_parse,
            site_ua=site_ua,
            site_headers=site_headers,
            site_proxy=site_proxy,
        )

    def add_rss_media(self, data: dict) -> RssAddResultDTO:
        """添加RSS订阅（支持批量多季）"""
        channel = RssType.Manual if data.get("in_form") == "manual" else RssType.Auto
        name = data.get("name")
        year = data.get("year")
        season = data.get("season")
        mtype = MediaType.MOVIE if data.get("type") in MovieTypes else MediaType.TV
        media_info = None
        code = 0
        msg = ""

        kwargs = {
            "mtype": mtype,
            "name": name,
            "year": year,
            "channel": channel,
            "keyword": data.get("keyword"),
            "fuzzy_match": data.get("fuzzy_match"),
            "mediaid": data.get("mediaid"),
            "rss_sites": data.get("rss_sites"),
            "search_sites": data.get("search_sites"),
            "over_edition": data.get("over_edition"),
            "filter_restype": data.get("filter_restype"),
            "filter_pix": data.get("filter_pix"),
            "filter_team": data.get("filter_team"),
            "filter_rule": data.get("filter_rule"),
            "filter_include": data.get("filter_include"),
            "filter_exclude": data.get("filter_exclude"),
            "save_path": data.get("save_path"),
            "download_setting": data.get("download_setting"),
        }

        if isinstance(season, list):
            for sea in season:
                kwargs["season"] = sea
                kwargs.pop("total_ep", None)
                kwargs.pop("current_ep", None)
                code, msg, media_info = self._subscribe.add_rss_subscribe(**kwargs)
                if code != 0:
                    break
        else:
            kwargs["season"] = season
            kwargs["total_ep"] = data.get("total_ep")
            kwargs["current_ep"] = data.get("current_ep")
            code, msg, media_info = self._subscribe.add_rss_subscribe(**kwargs)

        rssid = None
        if media_info:
            rssid = self._subscribe.get_subscribe_id(mtype=mtype, title=name or "", tmdbid=media_info.tmdb_id)

        return RssAddResultDTO(code=code, msg=msg, rssid=rssid, media_info=media_info)

    def update_rss_media(self, data: dict) -> RssAddResultDTO:
        """更新RSS订阅（支持批量多季）"""
        name = data.get("name")
        year = data.get("year")
        season = data.get("season")
        mtype = MediaType.MOVIE if data.get("type") in MovieTypes else MediaType.TV
        rssid = data.get("rssid")
        media_info = None
        code = 0
        msg = ""

        if not rssid:
            return RssAddResultDTO(code=-1, msg="缺少订阅ID", rssid=None, media_info=None)

        kwargs = {
            "mtype": mtype,
            "rssid": rssid,
            "name": name,
            "year": year,
            "keyword": data.get("keyword"),
            "fuzzy_match": data.get("fuzzy_match"),
            "mediaid": data.get("mediaid"),
            "rss_sites": data.get("rss_sites"),
            "search_sites": data.get("search_sites"),
            "over_edition": data.get("over_edition"),
            "filter_restype": data.get("filter_restype"),
            "filter_pix": data.get("filter_pix"),
            "filter_team": data.get("filter_team"),
            "filter_rule": data.get("filter_rule"),
            "filter_include": data.get("filter_include"),
            "filter_exclude": data.get("filter_exclude"),
            "save_path": data.get("save_path"),
            "download_setting": data.get("download_setting"),
            "image": data.get("image"),
        }

        if isinstance(season, list):
            for sea in season:
                kwargs["season"] = sea
                kwargs.pop("total_ep", None)
                kwargs.pop("current_ep", None)
                code, msg, media_info = self._subscribe.update_rss_subscribe(**kwargs)
                if code != 0:
                    break
        else:
            kwargs["season"] = season
            kwargs["total_ep"] = data.get("total_ep")
            kwargs["current_ep"] = data.get("current_ep")
            code, msg, media_info = self._subscribe.update_rss_subscribe(**kwargs)

        return RssAddResultDTO(code=code, msg=msg, rssid=rssid, media_info=media_info)

    def re_rss_history(self, rssid: str, rtype: str) -> tuple[int, str]:
        """从历史记录重新订阅"""
        if not self._rss:
            self._rss = Rss()
        rssinfo = self._rss.get_rss_history(rtype=rtype, rid=rssid)
        if not rssinfo:
            return -1, "订阅历史记录不存在"
        mtype = MediaType.MOVIE if rtype == "MOV" else MediaType.TV
        if rssinfo[0].SEASON:
            season = int(str(rssinfo[0].SEASON).replace("S", ""))
        else:
            season = None
        code, msg, _ = self._subscribe.add_rss_subscribe(
            mtype=mtype,
            name=rssinfo[0].NAME,
            year=rssinfo[0].YEAR,
            channel=RssType.Auto.value,
            season=season,
            mediaid=rssinfo[0].TMDBID,
            total_ep=rssinfo[0].TOTAL,
            current_ep=rssinfo[0].START,
        )
        return code, msg

    def remove_rss_media(
        self, name: str, mtype: str, year: str, season: int | None, rssid: str | None, tmdbid: str | None
    ) -> None:
        """移除RSS订阅"""
        if not str(tmdbid).isdigit():
            tmdbid = None
        if name:
            name = meta_info(title=name).get_name()
        if mtype:
            if mtype in MovieTypes:
                self._subscribe.delete_subscribe(
                    mtype=MediaType.MOVIE,
                    title=name or "",
                    year=year,
                    rssid=int(rssid) if rssid else None,
                    tmdbid=tmdbid,
                )
            else:
                self._subscribe.delete_subscribe(
                    mtype=MediaType.TV,
                    title=name or "",
                    season=str(season) if season is not None else None,
                    rssid=int(rssid) if rssid else None,
                    tmdbid=tmdbid,
                )

    def get_rss_detail(self, rid: str, rsstype: str) -> RssDetailResultDTO | None:
        """获取订阅详情"""
        if rsstype in MovieTypes:
            rssdetail = self._subscribe.get_subscribe_movies(rid=int(rid) if rid else None)
            if not rssdetail:
                return None
            detail = list(rssdetail.values())[0]
            detail["type"] = "MOV"
        else:
            rssdetail = self._subscribe.get_subscribe_tvs(rid=int(rid) if rid else None)
            if not rssdetail:
                return None
            detail = list(rssdetail.values())[0]
            detail["type"] = "TV"
        return RssDetailResultDTO(detail=detail)

    def get_default_rss_setting(self, mtype: str) -> dict | None:
        """获取默认订阅设置"""
        if mtype == "TV":
            return self._subscribe.default_rss_setting_tv
        elif mtype == "MOV":
            return self._subscribe.default_rss_setting_mov
        return {}

    def get_movie_rss_items(self) -> list[dict]:
        """获取电影订阅项目列表"""
        return [
            {"id": movie.get("tmdbid"), "rssid": movie.get("id")}
            for movie in self._subscribe.get_subscribe_movies().values()
            if movie.get("tmdbid")
        ]

    def get_tv_rss_items(self) -> list[dict]:
        """获取电视剧订阅项目列表（含去重）"""
        rss_tv_items = [
            {
                "id": tv.get("tmdbid"),
                "rssid": tv.get("id"),
                "season": int(str(tv.get("season")).replace("S", "")),
                "name": tv.get("name"),
            }
            for tv in self._subscribe.get_subscribe_tvs().values()
            if tv.get("season") and tv.get("tmdbid")
        ]
        if not self._rss_checker:
            self._rss_checker = RssTaskService()
        rss_tv_items += self._rss_checker.get_userrss_mediainfos()
        uniques = set()
        unique_tv_items = []
        for item in rss_tv_items:
            unique = f"{item.get('id')}_{item.get('season')}"
            if unique not in uniques:
                uniques.add(unique)
                unique_tv_items.append(item)
        return unique_tv_items

    def get_movie_rss_list(self) -> dict:
        return self._subscribe.get_subscribe_movies()

    def get_tv_rss_list(self) -> dict:
        return self._subscribe.get_subscribe_tvs()

    def get_rss_history(self, mtype: str) -> list[dict]:
        if not self._rss:
            self._rss = Rss()
        return [rec.as_dict() for rec in self._rss.get_rss_history(rtype=mtype)]

    def delete_rss_history(self, rssid: str) -> None:
        if not self._rss:
            self._rss = Rss()
        self._rss.delete_rss_history(rssid=rssid)

    def refresh_rss(self, mtype: str, rssid: str) -> None:
        """后台刷新RSS搜索"""

        if mtype == "MOV":
            ThreadHelper().start_thread(self._subscribe.subscribe_search_movie, (rssid,))
        else:
            ThreadHelper().start_thread(self._subscribe.subscribe_search_tv, (rssid,))

    def truncate_rss_history(self) -> None:

        RssHelper().truncate_rss_history()
        self._subscribe.truncate_rss_episodes()

    def get_ical_events(self) -> list[dict]:
        """获取RSS日历事件"""
        from app.services.media_service import MediaInfoService

        media_service = MediaInfoService()
        events = []
        for movie in self.get_movie_rss_items():
            info = media_service.get_movie_calendar(tid=movie.get("id"), rssid=movie.get("rssid"))
            if info and info.get("id"):
                events.append(info)
        for tv in self.get_tv_rss_items():
            infos = media_service.get_tv_calendar(
                tid=tv.get("id"), season=tv.get("season"), name=tv.get("name"), rssid=tv.get("rssid")
            )
            if infos and isinstance(infos, list):
                for info in infos:
                    if info.get("id"):
                        events.append(info)
        return events

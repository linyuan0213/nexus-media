"""
SubscribeService - 订阅业务 Facade
将 app/subscribe.py 中的复杂业务逻辑下沉到可独立测试的 Service。
按 Clean Architecture 拆分为：
- SubscribeSearchEngine：订阅搜索/下载逻辑（app/services/subscribe_search_engine.py）
- SubscribeService：对外保留的入口类（兼容旧调用 Subscribe）
"""

import json
from typing import Any

import log
from app.core.system_config import SystemConfig
from app.db.repositories.rss_repo_adapter import (
    RssHistoryRepositoryAdapter,
    RssMovieRepositoryAdapter,
    RssTvEpisodeRepositoryAdapter,
    RssTvRepositoryAdapter,
)
from app.media import DouBan, MediaService, meta_info
from app.message import Message
from app.plugin_framework.event_compat import EventManager
from app.services.downloader_core import DownloaderCore as Downloader
from app.services.filter_service import FilterService as Filter
from app.services.indexer_service import IndexerService
from app.services.subscribe_search_engine import SubscribeSearchEngine
from app.sites import Sites
from app.utils.types import EventType, MediaType, RssType, SystemConfigKey
from app.utils.web_utils import WebUtils


class SubscribeService:
    """
    订阅业务 Facade
    保留与原 Subscribe 兼容的公共 API
    """

    def __init__(
        self,
        movie_repo: Any | None = None,
        tv_repo: Any | None = None,
        tv_episode_repo: Any | None = None,
        history_repo: Any | None = None,
        search_engine: SubscribeSearchEngine | None = None,
        message: Message | None = None,
        media_service: MediaService | None = None,
        downloader: Downloader | None = None,
        sites: Sites | None = None,
        douban: DouBan | None = None,
        indexer_service: IndexerService | None = None,
        filter_service: Filter | None = None,
        eventmanager: EventManager | None = None,
        system_config: SystemConfig | None = None,
    ):
        self._movie_repo = movie_repo or RssMovieRepositoryAdapter()
        self._tv_repo = tv_repo or RssTvRepositoryAdapter()
        self._tv_episode_repo = tv_episode_repo or RssTvEpisodeRepositoryAdapter()
        self._history_repo = history_repo or RssHistoryRepositoryAdapter()
        self._search_engine = search_engine or SubscribeSearchEngine(
            service=self, movie_repo=self._movie_repo, tv_repo=self._tv_repo, tv_episode_repo=self._tv_episode_repo
        )
        self._message = message or Message()
        self._media = media_service or MediaService()
        self._downloader = downloader or Downloader()
        self._sites = sites or Sites()
        self._douban = douban or DouBan()
        self._indexer_service = indexer_service or IndexerService()
        self._filter = filter_service or Filter()
        self._eventmanager = eventmanager or EventManager()
        self._system_config = system_config or SystemConfig()

    @property
    def default_rss_setting_tv(self) -> dict | None:
        return self._system_config.get(SystemConfigKey.DefaultRssSettingTV) or {}

    @property
    def default_rss_setting_mov(self) -> dict | None:
        return self._system_config.get(SystemConfigKey.DefaultRssSettingMOV) or {}

    def update_rss_subscribe(
        self,
        mtype: Any,
        rssid: int | None,
        name: str | None = None,
        year: Any = None,
        keyword: str | None = None,
        season: int | None = None,
        fuzzy_match: bool = False,
        mediaid: str | None = None,
        rss_sites: list[str] | str | None = None,
        search_sites: list[str] | str | None = None,
        over_edition: bool | int = False,
        filter_restype: str | None = None,
        filter_pix: str | None = None,
        filter_team: str | None = None,
        filter_rule: int | str | None = None,
        filter_include: str | None = None,
        filter_exclude: str | None = None,
        save_path: str | None = None,
        download_setting: int | str | None = None,
        total_ep: int | None = None,
        current_ep: int | None = None,
        state: str = "D",
        in_from: str | None = None,
        user_name: str | None = None,
        image: str | None = None,
    ) -> tuple[int, str, Any]:
        """
        更新电影、电视剧订阅
        :param mtype: 类型，电影、电视剧、动漫
        :param rssid: 订阅ID
        :param name: 标题
        :param year: 年份
        :param keyword: 自定义搜索词
        :param season: 第几季，数字
        :param fuzzy_match: 是否模糊匹配
        :param mediaid: 媒体ID，DB:/BG:/TMDBID
        :param rss_sites: 订阅站点列表
        :param search_sites: 搜索站点列表
        :param over_edition: 是否选版
        :param filter_restype: 质量过滤
        :param filter_pix: 分辨率过滤
        :param filter_team: 制作组/字幕组过滤
        :param filter_rule: 关键字过滤
        :param filter_include: 包含关键字
        :param filter_exclude: 排除关键字
        :param save_path: 保存路径
        :param download_setting: 下载设置
        :param total_ep: 总集数
        :param current_ep: 开始订阅集数
        :param state: 状态
        :param in_from: 来源
        :param user_name: 用户名
        :return: 错误码：0 代表成功，错误信息
        """
        if not rssid:
            return -1, "缺少订阅ID", None

        year = int(str(year)) if str(year).isdigit() else ""
        rss_sites = rss_sites or []
        if isinstance(rss_sites, str):
            rss_sites = rss_sites.split(",")
        search_sites = search_sites or []
        if isinstance(search_sites, str):
            search_sites = search_sites.split(",")
        over_edition = 1 if over_edition else 0
        filter_rule = int(filter_rule) if str(filter_rule).isdigit() else None
        total_ep = int(total_ep) if str(total_ep).isdigit() else None
        current_ep = int(current_ep) if str(current_ep).isdigit() else None
        download_setting = int(download_setting) if str(download_setting).replace("-", "").isdigit() else None
        fuzzy_match = bool(fuzzy_match)

        media_info = None
        # 搜索媒体信息
        if not fuzzy_match:
            if mediaid:
                media_info = WebUtils.get_mediainfo_from_id(mtype=mtype, mediaid=mediaid)
                if not season and media_info:
                    season = media_info.begin_season
            else:
                if season:
                    title = "%s %s 第%s季".strip() % (name, year, season)
                else:
                    title = "%s %s".strip() % (name, year)
                media_info = self._media.get_media_info(
                    title=title, mtype=mtype, strict=bool(year), cache=False
                )
            if not media_info or not media_info.tmdb_info:
                return 1, "TMDB无法查询到媒体信息", None
            if media_info.type != MediaType.MOVIE:
                if not season and str(mediaid).startswith("DB:"):
                    season = 1
                if season:
                    total_episode = (
                        total_ep
                        if total_ep
                        else self._media.get_tmdb_season_episodes_num(tv_info=media_info.tmdb_info, season=int(season))
                    )
                else:
                    total_seasoninfo = self._media.get_tmdb_tv_seasons(tv_info=media_info.tmdb_info)
                    if not total_seasoninfo:
                        return 2, "获取剧集信息失败", media_info
                    total_seasoninfo = sorted(total_seasoninfo, key=lambda x: x.get("season_number"), reverse=True)
                    season = total_seasoninfo[0].get("season_number")
                    total_episode = total_seasoninfo[0].get("episode_count")
                if not total_episode:
                    return 3, f"第{season}季获取剧集数失败，请确认该季是否存在", media_info
                media_info.begin_season = int(season)
                media_info.total_episodes = total_episode
                if total_ep:
                    total = total_ep
                else:
                    total = media_info.total_episodes
                if current_ep:
                    lack = total - current_ep - 1
                else:
                    lack = total
                season_str = media_info.get_season_string()
                code = self._tv_repo.update(
                    rssid=int(rssid),
                    name=media_info.title,
                    year=media_info.year,
                    season=season_str,
                    tmdbid=media_info.tmdb_id,
                    image=image or media_info.get_message_image(),
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
                    total=total,
                    lack=lack,
                    state=state,
                    desc=media_info.overview,
                    note=self.gen_rss_note(media_info),
                    keyword=keyword,
                    fuzzy_match=0,
                )
            else:
                code = self._movie_repo.update(
                    rssid=int(rssid),
                    name=media_info.title,
                    year=media_info.year,
                    tmdbid=media_info.tmdb_id,
                    image=image or media_info.get_message_image(),
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
                    state=state,
                    desc=media_info.overview,
                    note=self.gen_rss_note(media_info),
                    keyword=keyword,
                    fuzzy_match=0,
                )
        else:
            media_info = meta_info(title=name, mtype=mtype)
            media_info.title = name
            media_info.type = mtype
            if season:
                media_info.begin_season = int(season)
            if mtype == MediaType.MOVIE:
                code = self._movie_repo.update(
                    rssid=int(rssid),
                    name=name,
                    year=year,
                    image=image,
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
                    state=state,
                    keyword=keyword,
                    fuzzy_match=1,
                )
            else:
                season_str = media_info.get_season_string() if media_info.begin_season else ""
                code = self._tv_repo.update(
                    rssid=int(rssid),
                    name=name,
                    year=year,
                    season=season_str,
                    image=image,
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
                    total=0,
                    lack=0,
                    state=state,
                    keyword=keyword,
                    fuzzy_match=1,
                )

        if code == 0:
            self._eventmanager.send_event(
                EventType.SubscribeAdd,
                {
                    "media": media_info.to_dict() if media_info else {},
                    "rssid": rssid,
                    "rss_sites": rss_sites,
                    "search_sites": search_sites,
                    "over_edition": over_edition,
                    "filter_restype": filter_restype,
                    "filter_pix": filter_pix,
                    "filter_team": filter_team,
                    "filter_rule": filter_rule,
                    "save_path": save_path,
                    "download_setting": download_setting,
                    "total_ep": total_ep,
                    "current_ep": current_ep,
                    "fuzzy_match": fuzzy_match,
                    "keyword": keyword,
                },
            )
            if in_from:
                if media_info:
                    media_info.user_name = user_name
                    self._message.send_rss_success_message(in_from=in_from, media_info=media_info)
            return code, "更新订阅成功", media_info
        else:
            return code, "更新订阅失败", media_info

    def add_rss_subscribe(
        self,
        mtype: Any,
        name: str | None,
        year: Any,
        channel: str | None = None,
        keyword: str | None = None,
        season: int | None = None,
        fuzzy_match: bool = False,
        mediaid: str | None = None,
        rss_sites: list[str] | str | None = None,
        search_sites: list[str] | str | None = None,
        over_edition: bool | int = False,
        filter_restype: str | None = None,
        filter_pix: str | None = None,
        filter_team: str | None = None,
        filter_rule: int | str | None = None,
        filter_include: str | None = None,
        filter_exclude: str | None = None,
        save_path: str | None = None,
        download_setting: int | str | None = None,
        total_ep: int | None = None,
        current_ep: int | None = None,
        state: str = "D",
        rssid: int | None = None,
        in_from: str | None = None,
        user_name: str | None = None,
    ) -> tuple[int, str, Any]:
        """
        添加电影、电视剧订阅
        :param mtype: 类型，电影、电视剧、动漫
        :param name: 标题
        :param year: 年份，如要是剧集需要是首播年份
        :param channel: 自动或手动
        :param keyword: 自定义搜索词
        :param season: 第几季，数字
        :param fuzzy_match: 是否模糊匹配
        :param mediaid: 媒体ID，DB:/BG:/TMDBID
        :param rss_sites: 订阅站点列表，为空则表示全部站点
        :param search_sites: 搜索站点列表，为空则表示全部站点
        :param over_edition: 是否选版
        :param filter_restype: 质量过滤
        :param filter_pix: 分辨率过滤
        :param filter_team: 制作组/字幕组过滤
        :param filter_rule: 关键字过滤
        :param filter_include: 包含关键字
        :param filter_exclude: 排除关键字
        :param save_path: 保存路径
        :param download_setting: 下载设置
        :param state: 添加订阅时的状态
        :param rssid: 修改订阅时传入
        :param total_ep: 总集数
        :param current_ep: 开始订阅集数
        :param in_from: 来源
        :param user_name: 用户名
        :return: 错误码：0 代表成功，错误信息
        """
        if not name:
            return -1, "标题或类型有误", None
        year = int(year) if str(year).isdigit() else ""
        rss_sites = rss_sites or []
        if isinstance(rss_sites, str):
            rss_sites = rss_sites.split(",")
        search_sites = search_sites or []
        if isinstance(search_sites, str):
            search_sites = search_sites.split(",")
        over_edition = 1 if over_edition else 0
        filter_rule = int(filter_rule) if str(filter_rule).isdigit() else None
        total_ep = int(total_ep) if str(total_ep).isdigit() else None
        current_ep = int(current_ep) if str(current_ep).isdigit() else None
        download_setting = int(download_setting) if str(download_setting).replace("-", "").isdigit() else None
        fuzzy_match = bool(fuzzy_match)
        # 仅在新增订阅（无 rssid）时应用默认设置，避免编辑时被默认值覆盖
        if channel == RssType.Auto and not rssid:
            default_rss_setting = (
                self.default_rss_setting_tv
                if mtype in [MediaType.TV, MediaType.ANIME]
                else self.default_rss_setting_mov
            )
            if default_rss_setting:
                default_restype = default_rss_setting.get("restype")
                default_pix = default_rss_setting.get("pix")
                default_team = default_rss_setting.get("team")
                default_rule = default_rss_setting.get("rule")
                default_include = default_rss_setting.get("include")
                default_exclude = default_rss_setting.get("exclude")
                default_download_setting = default_rss_setting.get("download_setting")
                default_over_edition = default_rss_setting.get("over_edition")
                default_rss_sites = default_rss_setting.get("rss_sites")
                default_search_sites = default_rss_setting.get("search_sites")
                if not filter_restype and default_restype:
                    filter_restype = default_restype
                if not filter_pix and default_pix:
                    filter_pix = default_pix
                if not filter_team and default_team:
                    filter_team = default_team
                if not filter_rule and default_rule:
                    filter_rule = int(default_rule) if str(default_rule).isdigit() else None
                if not filter_include and default_include:
                    filter_include = default_include
                if not filter_exclude and default_exclude:
                    filter_exclude = default_exclude
                if not over_edition and default_over_edition:
                    over_edition = 1 if default_over_edition == "1" else 0
                if not download_setting and default_download_setting:
                    download_setting = (
                        int(default_download_setting)
                        if str(default_download_setting).replace("-", "").isdigit()
                        else None
                    )
                if not rss_sites and default_rss_sites:
                    rss_sites = default_rss_sites
                if not search_sites and default_search_sites:
                    search_sites = default_search_sites
        # 搜索媒体信息
        if not fuzzy_match:
            # 根据TMDBID查询，从推荐加订阅的情况
            if mediaid:
                # 根据ID查询
                media_info = WebUtils.get_mediainfo_from_id(mtype=mtype, mediaid=mediaid)
                if not season and media_info:
                    season = media_info.begin_season
            else:
                # 根据名称和年份查询
                if season:
                    title = "%s %s 第%s季".strip() % (name, year, season)
                else:
                    title = "%s %s".strip() % (name, year)
                media_info = self._media.get_media_info(
                    title=title, mtype=mtype, strict=bool(year), cache=False
                )
            # 检查TMDB信息
            if not media_info or not media_info.tmdb_info:
                return 1, "TMDB无法查询到媒体信息", None
            # 添加订阅
            if media_info.type != MediaType.MOVIE:
                # 电视剧
                # 豆瓣来的电视剧且没有季数时，设为第一季
                if not season and str(mediaid).startswith("DB:"):
                    season = 1
                if season:
                    total_episode = (
                        total_ep
                        if total_ep
                        else self._media.get_tmdb_season_episodes_num(tv_info=media_info.tmdb_info, season=int(season))
                    )
                else:
                    # 查询季及集信息
                    total_seasoninfo = self._media.get_tmdb_tv_seasons(tv_info=media_info.tmdb_info)
                    if not total_seasoninfo:
                        return 2, "获取剧集信息失败", media_info
                    # 按季号降序排序
                    total_seasoninfo = sorted(total_seasoninfo, key=lambda x: x.get("season_number"), reverse=True)
                    # 取最新季
                    season = total_seasoninfo[0].get("season_number")
                    total_episode = total_seasoninfo[0].get("episode_count")
                if not total_episode:
                    return 3, f"第{season}季获取剧集数失败，请确认该季是否存在", media_info
                media_info.begin_season = int(season)
                media_info.total_episodes = total_episode
                if total_ep:
                    total = total_ep
                else:
                    total = media_info.total_episodes
                if current_ep:
                    lack = total - current_ep - 1
                else:
                    lack = total
                code = self._tv_repo.insert(
                    media_info=media_info,
                    total=total,
                    lack=lack,
                    state=state,
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
                    fuzzy_match=0,
                    desc=media_info.overview,
                    note=self.gen_rss_note(media_info),
                    keyword=keyword,
                )
            else:
                # 电影
                code = self._movie_repo.insert(
                    media_info=media_info,
                    state=state,
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
                    fuzzy_match=0,
                    desc=media_info.overview,
                    note=self.gen_rss_note(media_info),
                    keyword=keyword,
                )
        else:
            # 模糊匹配
            media_info = meta_info(title=name, mtype=mtype)
            media_info.title = name
            media_info.type = mtype
            if season:
                media_info.begin_season = int(season)
            if mtype == MediaType.MOVIE:
                code = self._movie_repo.insert(
                    media_info=media_info,
                    state="R",
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
                    fuzzy_match=1,
                    keyword=keyword,
                )
            else:
                code = self._tv_repo.insert(
                    media_info=media_info,
                    total=0,
                    lack=0,
                    state="R",
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
                    fuzzy_match=1,
                    keyword=keyword,
                )

        if code == 0:
            # 解发事件
            self._eventmanager.send_event(
                EventType.SubscribeAdd,
                {
                    "media": media_info.to_dict(),
                    "rssid": rssid,
                    "rss_sites": rss_sites,
                    "search_sites": search_sites,
                    "over_edition": over_edition,
                    "filter_restype": filter_restype,
                    "filter_pix": filter_pix,
                    "filter_team": filter_team,
                    "filter_rule": filter_rule,
                    "save_path": save_path,
                    "download_setting": download_setting,
                    "total_ep": total_ep,
                    "current_ep": current_ep,
                    "fuzzy_match": fuzzy_match,
                    "keyword": keyword,
                },
            )
            # 发送订阅成功消息
            if in_from:
                media_info.user_name = user_name
                self._message.send_rss_success_message(in_from=in_from, media_info=media_info)
            return code, "添加订阅成功", media_info
        elif code == 9:
            return code, "订阅已存在", media_info
        else:
            return code, "添加订阅失败", media_info

    def finish_rss_subscribe(self, rssid: int | None, media: Any) -> None:
        """
        完成订阅
        :param rssid: 订阅ID
        :param media: 识别的媒体信息，发送消息使用
        """
        if not rssid or not media:
            return
        # 电影订阅
        rtype = "MOV" if media.type == MediaType.MOVIE else "TV"
        if media.type == MediaType.MOVIE:
            # 查询电影RSS数据
            rss = self._movie_repo.get_all(rssid=rssid)
            if not rss:
                return
            # 登记订阅历史
            self._history_repo.insert(
                rssid=rssid,
                rtype=rtype,
                name=rss[0].NAME,
                year=rss[0].YEAR,
                tmdbid=rss[0].TMDBID,
                image=media.get_poster_image(),
                desc=media.overview,
            )

            # 删除订阅
            self.delete_subscribe(mtype=MediaType.MOVIE, rssid=rssid)

        # 电视剧订阅
        else:
            # 查询电视剧RSS数据
            rss = self._tv_repo.get_all(rssid=rssid)
            if not rss:
                return
            total = rss[0].TOTAL_EP
            # 登记订阅历史
            self._history_repo.insert(
                rssid=rssid,
                rtype=rtype,
                name=rss[0].NAME,
                year=rss[0].YEAR,
                season=rss[0].SEASON,
                tmdbid=rss[0].TMDBID,
                image=media.get_poster_image(),
                desc=media.overview,
                total=total,
                start=rss[0].CURRENT_EP,
            )
            # 删除订阅
            self.delete_subscribe(mtype=MediaType.TV, rssid=rssid)

        # 解发事件
        self._eventmanager.send_event(EventType.SubscribeFinished, {"media_info": media.to_dict(), "rssid": rssid})

        # 发送订阅完成的消息
        log.info(
            f"【Rss】{media.type.value} {media.get_title_string()} {media.get_season_string()} 订阅完成，删除订阅..."
        )
        self._message.send_rss_finished_message(media_info=media)

    def get_subscribe_movies(self, rid: int | None = None, state: str | None = None) -> dict:
        """
        获取电影订阅
        """
        ret_dict = {}
        rss_movies = self._movie_repo.get_all(rssid=rid, state=state)
        rss_sites_valid = self._sites.get_site_names(rss=True)
        search_sites_valid = self._indexer_service.get_user_indexer_names()
        for rss_movie in rss_movies:
            desc = rss_movie.DESC
            note = rss_movie.NOTE
            tmdbid = rss_movie.TMDBID
            rss_sites = json.loads(rss_movie.RSS_SITES) if rss_movie.RSS_SITES else []
            search_sites = json.loads(rss_movie.SEARCH_SITES) if rss_movie.SEARCH_SITES else []
            over_edition = rss_movie.OVER_EDITION == 1
            filter_restype = rss_movie.FILTER_RESTYPE
            filter_pix = rss_movie.FILTER_PIX
            filter_team = rss_movie.FILTER_TEAM
            filter_rule = rss_movie.FILTER_RULE
            filter_include = rss_movie.FILTER_INCLUDE
            filter_exclude = rss_movie.FILTER_EXCLUDE
            download_setting = rss_movie.DOWNLOAD_SETTING
            save_path = rss_movie.SAVE_PATH
            fuzzy_match = rss_movie.FUZZY_MATCH == 1
            keyword = rss_movie.KEYWORD
            # 兼容旧配置
            if desc and desc.find("{") != -1:
                desc = self.__parse_rss_desc(desc)
                rss_sites = desc.get("rss_sites")
                search_sites = desc.get("search_sites")
                over_edition = desc.get("over_edition") == "Y"
                filter_restype = desc.get("restype")
                filter_pix = desc.get("pix")
                filter_team = desc.get("team")
                filter_rule = desc.get("rule")
                download_setting = ""
                save_path = ""
                fuzzy_match = not tmdbid
            if note:
                note_info = self.__parse_rss_desc(note)
            else:
                note_info = {}
            rss_sites = [site for site in rss_sites if site in rss_sites_valid]
            search_sites = [site for site in search_sites if site in search_sites_valid]
            ret_dict[str(rss_movie.ID)] = {
                "id": rss_movie.ID,
                "name": rss_movie.NAME,
                "year": rss_movie.YEAR,
                "tmdbid": rss_movie.TMDBID,
                "image": rss_movie.IMAGE,
                "overview": rss_movie.DESC,
                "rss_sites": rss_sites,
                "search_sites": search_sites,
                "over_edition": over_edition,
                "filter_restype": filter_restype,
                "filter_pix": filter_pix,
                "filter_team": filter_team,
                "filter_rule": filter_rule,
                "filter_include": filter_include,
                "filter_exclude": filter_exclude,
                "save_path": save_path,
                "download_setting": download_setting,
                "fuzzy_match": fuzzy_match,
                "state": rss_movie.STATE,
                "poster": note_info.get("poster"),
                "release_date": note_info.get("release_date"),
                "vote": note_info.get("vote"),
                "keyword": keyword,
            }
        return ret_dict

    def get_subscribe_tvs(self, rid: int | None = None, state: str | None = None) -> dict:
        ret_dict = {}
        rss_tvs = self._tv_repo.get_all(rssid=rid, state=state)
        rss_sites_valid = self._sites.get_site_names(rss=True)
        search_sites_valid = self._indexer_service.get_user_indexer_names()
        for rss_tv in rss_tvs:
            desc = rss_tv.DESC
            note = rss_tv.NOTE
            tmdbid = rss_tv.TMDBID
            rss_sites = json.loads(rss_tv.RSS_SITES) if rss_tv.RSS_SITES else []
            search_sites = json.loads(rss_tv.SEARCH_SITES) if rss_tv.SEARCH_SITES else []
            over_edition = rss_tv.OVER_EDITION == 1
            filter_restype = rss_tv.FILTER_RESTYPE
            filter_pix = rss_tv.FILTER_PIX
            filter_team = rss_tv.FILTER_TEAM
            filter_rule = rss_tv.FILTER_RULE
            filter_include = rss_tv.FILTER_INCLUDE
            filter_exclude = rss_tv.FILTER_EXCLUDE
            download_setting = rss_tv.DOWNLOAD_SETTING
            save_path = rss_tv.SAVE_PATH
            total_ep = rss_tv.TOTAL_EP
            current_ep = rss_tv.CURRENT_EP
            fuzzy_match = rss_tv.FUZZY_MATCH == 1
            keyword = rss_tv.KEYWORD
            # 兼容旧配置
            if desc and desc.find("{") != -1:
                desc = self.__parse_rss_desc(desc)
                rss_sites = desc.get("rss_sites")
                search_sites = desc.get("search_sites")
                over_edition = desc.get("over_edition") == "Y"
                filter_restype = desc.get("restype")
                filter_pix = desc.get("pix")
                filter_team = desc.get("team")
                filter_rule = desc.get("rule")
                filter_include = desc.get("include")
                filter_exclude = desc.get("exclude")
                save_path = ""
                download_setting = ""
                total_ep = desc.get("total")
                current_ep = desc.get("current")
                fuzzy_match = not tmdbid
            if note:
                note_info = self.__parse_rss_desc(note)
            else:
                note_info = {}
            rss_sites = [site for site in rss_sites if site in rss_sites_valid]
            search_sites = [site for site in search_sites if site in search_sites_valid]
            ret_dict[str(rss_tv.ID)] = {
                "id": rss_tv.ID,
                "name": rss_tv.NAME,
                "year": rss_tv.YEAR,
                "season": rss_tv.SEASON,
                "tmdbid": rss_tv.TMDBID,
                "image": rss_tv.IMAGE,
                "overview": rss_tv.DESC,
                "rss_sites": rss_sites,
                "search_sites": search_sites,
                "over_edition": over_edition,
                "filter_restype": filter_restype,
                "filter_pix": filter_pix,
                "filter_team": filter_team,
                "filter_rule": filter_rule,
                "filter_include": filter_include,
                "filter_exclude": filter_exclude,
                "save_path": save_path,
                "download_setting": download_setting,
                "total": rss_tv.TOTAL,
                "lack": rss_tv.LACK,
                "total_ep": total_ep,
                "current_ep": current_ep,
                "fuzzy_match": fuzzy_match,
                "state": rss_tv.STATE,
                "poster": note_info.get("poster"),
                "release_date": note_info.get("release_date"),
                "vote": note_info.get("vote"),
                "keyword": keyword,
            }
        return ret_dict

    @staticmethod
    def __parse_rss_desc(desc):
        """
        解析订阅的JSON字段
        """
        if not desc:
            return {}
        return json.loads(desc) or {}

    @staticmethod
    def gen_rss_note(media: Any) -> str:
        """
        生成订阅的JSON备注信息
        :param media: 媒体信息
        :return: 备注信息
        """
        if not media:
            return {}
        note = {"poster": media.get_poster_image(), "release_date": media.release_date, "vote": media.vote_average}
        return json.dumps(note)

    def refresh_rss_metainfo(self) -> None:
        """
        定时将豆瓣订阅转换为TMDB的订阅，并更新订阅的TMDB信息
        优化：只对没有 tmdbid 的订阅进行查询，有 tmdbid 的订阅延长刷新间隔
        """
        # 更新电影
        log.info("【Subscribe】开始刷新订阅TMDB信息...")
        rss_movies = self.get_subscribe_movies(state="R")
        for _rid, rss_info in rss_movies.items():
            # 跳过模糊匹配的
            if rss_info.get("fuzzy_match"):
                continue
            rssid = rss_info.get("id")
            name = rss_info.get("name")
            year = rss_info.get("year") or ""
            tmdbid = rss_info.get("tmdbid")

            # 如果已经有 tmdbid，跳过刷新（减少 API 调用）
            # 只有当没有 tmdbid 时才进行查询
            if tmdbid:
                log.debug(f"【Subscribe】电影 {name} 已有 TMDB ID {tmdbid}，跳过刷新")
                continue

            # 更新TMDB信息（使用缓存）
            media_info = self.__get_media_info(tmdbid=tmdbid, name=name, year=year, mtype=MediaType.MOVIE, cache=True)
            if media_info and media_info.tmdb_id and media_info.title != name:
                log.info(f"【Subscribe】检测到TMDB信息变化，更新电影订阅 {name} 为 {media_info.title}")
                # 更新订阅信息
                self._movie_repo.update_tmdb(
                    rid=rssid,
                    tmdbid=media_info.tmdb_id,
                    title=media_info.title,
                    year=media_info.year,
                    image=media_info.get_message_image(),
                    desc=media_info.overview,
                    note=self.gen_rss_note(media_info),
                )

        # 更新电视剧
        rss_tvs = self.get_subscribe_tvs(state="R")
        for _rid, rss_info in rss_tvs.items():
            # 跳过模糊匹配的
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

            # 如果已经有 tmdbid，跳过刷新（减少 API 调用）
            # 只有当没有 tmdbid 时才进行查询
            if tmdbid:
                log.debug(f"【Subscribe】电视剧 {name} 已有 TMDB ID {tmdbid}，跳过刷新")
                continue

            # 更新TMDB信息（使用缓存）
            media_info = self.__get_media_info(tmdbid=tmdbid, name=name, year=year, mtype=MediaType.TV, cache=True)
            if media_info and media_info.tmdb_id:
                # 获取总集数
                total_episode = self._media.get_tmdb_season_episodes_num(
                    tv_info=media_info.tmdb_info, season=int(str(season).replace("S", ""))
                )
                # 设置总集数的，不更新集数
                if total_ep:
                    total_episode = total_ep
                if total_episode and (name != media_info.title or total != total_episode):
                    # 新的缺失集数
                    lack_episode = total_episode - (total - lack)
                    log.info(
                        f"【Subscribe】检测到TMDB信息变化，更新电视剧订阅 {name} 为 {media_info.title}，总集数为：{total_episode}"
                    )
                    # 更新订阅信息
                    self._tv_repo.update_tmdb(
                        rid=rssid,
                        tmdbid=media_info.tmdb_id,
                        title=media_info.title,
                        year=media_info.year,
                        total=total_episode,
                        lack=lack_episode,
                        image=media_info.get_message_image(),
                        desc=media_info.overview,
                        note=self.gen_rss_note(media_info),
                    )
                    # 更新缺失季集
                    self._tv_episode_repo.update(
                        rid=rssid, episodes=range(total_episode - lack_episode + 1, total_episode + 1)
                    )
        log.info("【Subscribe】订阅TMDB信息刷新完成")

    def __get_media_info(self, tmdbid, name, year, mtype, cache=True):
        """
        综合返回媒体信息
        """
        if tmdbid and not str(tmdbid).startswith("DB:"):
            media_info = meta_info(title="%s %s".strip() % (name, year))
            tmdb_info = self._media.get_tmdb_info(mtype=mtype, tmdbid=tmdbid)
            media_info.set_tmdb_info(tmdb_info)
        else:
            media_info = self._media.get_media_info(title=f"{name} {year}", mtype=mtype, strict=True, cache=cache)
        return media_info

    def subscribe_search_all(self) -> None:
        """
        搜索R状态的所有订阅，由定时服务调用
        """
        self._search_engine.subscribe_search_all()

    def subscribe_search(self, state: str = "D") -> None:
        """
        RSS订阅队列中状态的任务处理，先进行存量资源搜索，缺失的才标志为RSS状态，由定时服务调用
        """
        self._search_engine.subscribe_search(state=state)

    def subscribe_search_movie(self, rssid: int | None = None, state: str = "D") -> None:
        """
        搜索电影RSS
        """
        self._search_engine.subscribe_search_movie(rssid=rssid, state=state)

    def subscribe_search_tv(self, rssid: int | None = None, state: str = "D") -> None:
        """
        搜索电视剧RSS
        """
        self._search_engine.subscribe_search_tv(rssid=rssid, state=state)

    def update_rss_state(self, rtype: str, rssid: int, state: str) -> None:
        """
        根据类型更新订阅状态
        :param rtype: 订阅类型
        :param rssid: 订阅ID
        :param state: 状态 R/D/S
        """
        if rtype == MediaType.MOVIE:
            self._movie_repo.update_state(rssid=rssid, state=state)
        else:
            self._tv_repo.update_state(rssid=rssid, state=state)

    def update_subscribe_over_edition(self, rtype: str, rssid: int | None, media: Any) -> bool:
        """
        更新洗版订阅
        :param rtype: 订阅类型
        :param rssid: 订阅ID
        :param media: 含订阅信息的媒体信息
        :return 完成订阅返回True，否则返回False
        """
        if not rssid or not media.res_order or not media.filter_rule or not media.res_order:
            return False
        # 更新订阅命中的优先级
        self._movie_repo.update_filter_order(rtype=media.type, rssid=rssid, res_order=media.res_order)
        # 检查是否匹配最高优先级规则
        over_edition_order = self._filter.get_rule_first_order(rulegroup=media.filter_rule)
        if int(media.res_order) >= int(over_edition_order):
            # 完成洗版订阅
            self.finish_rss_subscribe(rssid=rssid, media=media)
            return True
        else:
            self.update_rss_state(rtype=rtype, rssid=rssid, state="R")
        return False

    def check_subscribe_over_edition(self, rtype: str, rssid: int, res_order: int | None) -> bool:
        """
        检查洗版订阅的优先级
        :param rtype: 订阅类型
        :param rssid: 订阅ID
        :param res_order: 优先级
        :return 资源更优先返回True，否则返回False
        """
        pre_res_order = self._movie_repo.get_filter_order(rtype=rtype, rssid=rssid)
        if not pre_res_order:
            return True
        return int(pre_res_order) < int(res_order)

    def update_subscribe_tv_lack(self, rssid: int | None, media_info: Any, seasoninfo: list | None) -> None:
        """
        更新电视剧订阅缺失集数
        """
        self._tv_repo.update_state(rssid=rssid, state="R")
        if not seasoninfo:
            return
        for info in seasoninfo:
            if str(info.get("season")) == media_info.get_season_seq():
                if info.get("episodes"):
                    log.info(
                        "【Subscribe】更新电视剧 {} {} 缺失集数为 {}".format(media_info.get_title_string(), media_info.get_season_string(), len(info.get("episodes")))
                    )
                    self._tv_repo.update_lack(rssid=rssid, lack_episodes=info.get("episodes"))
                break

    def get_subscribe_tv_episodes(self, rssid: int | None) -> Any:
        """
        查询数据库中订阅的电视剧缺失集数
        """
        return self._tv_episode_repo.get(rssid)

    def check_history(self, type_str: str, name: str, year: str | None, season: str | None) -> bool:
        """
        检查订阅历史是否存在
        """
        return self._history_repo.check_exists(type_str=type_str, name=name, year=year, season=season)

    def delete_subscribe(
        self, mtype: MediaType, title: str | None = None, year: str | None = None, season: str | None = None, rssid: int | None = None, tmdbid: str | None = None
    ) -> Any:
        """
        删除电影订阅
        """
        if mtype == MediaType.MOVIE:
            return self._movie_repo.delete(title=title, year=year, rssid=rssid, tmdbid=tmdbid)
        else:
            return self._tv_repo.delete(title=title, season=season, rssid=rssid, tmdbid=tmdbid)

    def get_subscribe_id(
        self, mtype: MediaType, title: str, year: str | None = None, season: str | None = None, tmdbid: str | None = None
    ) -> Any:
        """
        获取订阅ID
        """
        if mtype == MediaType.MOVIE:
            return self._movie_repo.get_id(title=title, year=year, tmdbid=tmdbid)
        else:
            return self._tv_repo.get_id(title=title, year=year, season=season, tmdbid=tmdbid)

    def truncate_rss_episodes(self) -> None:
        """
        清空订阅缺失集数
        """
        self._tv_episode_repo.delete_all()

"""Subscribe add service - 添加订阅."""

from typing import Any, cast

from app.events import Event
from app.events.constants import SUBSCRIBE_ADD
from app.media import meta_info
from app.services.subscribe.utils import gen_rss_note
from app.utils.types import MediaType, RssType, SystemConfigKey
from app.utils.web_utils import WebUtils


class SubscribeAddService:
    """添加订阅服务"""

    def __init__(
        self,
        movie_repo,
        tv_repo,
        media_service,
        message,
        event_bus,
        system_config,
    ):
        self._movie_repo = movie_repo
        self._tv_repo = tv_repo
        self._media = media_service
        self._message = message
        self._event_bus = event_bus
        self._system_config = system_config

    @property
    def default_rss_setting_tv(self) -> dict | None:
        return self._system_config.get(SystemConfigKey.DefaultRssSettingTV) or {}

    @property
    def default_rss_setting_mov(self) -> dict | None:
        return self._system_config.get(SystemConfigKey.DefaultRssSettingMOV) or {}

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
        """添加电影、电视剧订阅"""
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
        filter_rule = int(str(filter_rule)) if str(filter_rule).isdigit() else None
        total_ep = int(str(total_ep)) if str(total_ep).isdigit() else None
        current_ep = int(str(current_ep)) if str(current_ep).isdigit() else None
        download_setting = int(str(download_setting)) if str(download_setting).replace("-", "").isdigit() else None
        fuzzy_match = bool(fuzzy_match)

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
                media_info = self._media.get_media_info(title=title, mtype=mtype, strict=bool(year), cache=False)
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
                media_info.begin_season = int(season or 0)
                media_info.total_episodes = total_episode
                if total_ep:
                    total = total_ep
                else:
                    total = media_info.total_episodes
                lack = max(0, total - (current_ep or 0))
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
                    note=gen_rss_note(media_info),
                    keyword=keyword,
                )
            else:
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
                    note=gen_rss_note(media_info),
                    keyword=keyword,
                )
        else:
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
            self._event_bus.publish(
                Event(
                    event_type=SUBSCRIBE_ADD,
                    payload={
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
                ),
            )
            if in_from:
                media_info.user_name = user_name
                self._message.send_rss_success_message(in_from=cast(RssType, in_from), media_info=media_info)
            return code, "添加订阅成功", media_info
        elif code == 9:
            return code, "订阅已存在", media_info
        else:
            return code, "添加订阅失败", media_info

import json
import time
import traceback
from typing import TYPE_CHECKING, Any

import jsonpath
from lxml import etree

import log
from app.db.repositories.config_repo_adapter import UserRssConfigRepositoryAdapter
from app.db.repositories.rss_repo_adapter import RssHistoryRepositoryAdapter
from app.helper import RssHelper
from app.media import MediaService, meta_info
from app.message import Message
from app.schemas.rss import (
    RssAddResultDTO,
    RssDetailResultDTO,
)
from app.services.downloader_core import DownloaderCore as Downloader
from app.services.filter_service import FilterService as Filter
from app.services.scheduler_core import SchedulerCore
from app.services.search_service import Searcher
from app.services.subscribe_service import SubscribeService as Subscribe
from app.utils import ExceptionUtils, RequestUtils, StringUtils
from app.utils.commons import SingletonMeta
from app.utils.config_tools import get_proxies
from app.utils.types import MediaType, MovieTypes, RssType, SearchType
from config import Config

if TYPE_CHECKING:
    from app.services.rss_checker_service import RssCheckerService
    from app.services.rss_core import Rss


class RssSubscriptionService:
    """
    RSS 订阅业务服务
    负责订阅添加/删除、历史管理、列表查询、日历事件、RSS下载
    """

    def __init__(self, subscribe: Subscribe | None = None, rss: "Rss | None" = None, rss_checker: "RssTaskService | None" = None):
        self._subscribe: Subscribe = subscribe or Subscribe()
        self._rss: Rss | None = rss
        self._rss_checker: "RssTaskService | None" = rss_checker

    def download_rss(self) -> None:
        """触发RSS订阅下载"""
        if not self._rss:
            from app.services.rss_core import Rss

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
            from app.services.rss_core import Rss

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
            rssid = self._subscribe.get_subscribe_id(mtype=mtype, title=name, tmdbid=media_info.tmdb_id)

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
            from app.services.rss_core import Rss

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
            channel=RssType.Auto,
            season=season,
            mediaid=rssinfo[0].TMDBID,
            total_ep=rssinfo[0].TOTAL,
            current_ep=rssinfo[0].START,
        )
        return code, msg

    def remove_rss_media(self, name: str, mtype: str, year: str, season: int | None, rssid: str | None, tmdbid: str | None) -> None:
        """移除RSS订阅"""
        if not str(tmdbid).isdigit():
            tmdbid = None
        if name:
            name = meta_info(title=name).get_name()
        if mtype:
            if mtype in MovieTypes:
                self._subscribe.delete_subscribe(
                    mtype=MediaType.MOVIE, title=name, year=year, rssid=rssid, tmdbid=tmdbid
                )
            else:
                self._subscribe.delete_subscribe(
                    mtype=MediaType.TV, title=name, season=season, rssid=rssid, tmdbid=tmdbid
                )

    def get_rss_detail(self, rid: str, rsstype: str) -> RssDetailResultDTO | None:
        """获取订阅详情"""
        if rsstype in MovieTypes:
            rssdetail = self._subscribe.get_subscribe_movies(rid=rid)
            if not rssdetail:
                return None
            detail = list(rssdetail.values())[0]
            detail["type"] = "MOV"
        else:
            rssdetail = self._subscribe.get_subscribe_tvs(rid=rid)
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
            from app.services.rss_core import Rss

            self._rss = Rss()
        return [rec.as_dict() for rec in self._rss.get_rss_history(rtype=mtype)]

    def delete_rss_history(self, rssid: str) -> None:
        if not self._rss:
            from app.services.rss_core import Rss

            self._rss = Rss()
        self._rss.delete_rss_history(rssid=rssid)

    def refresh_rss(self, mtype: str, rssid: str) -> None:
        """后台刷新RSS搜索"""
        from app.helper import ThreadHelper

        if mtype == "MOV":
            ThreadHelper().start_thread(self._subscribe.subscribe_search_movie, (rssid,))
        else:
            ThreadHelper().start_thread(self._subscribe.subscribe_search_tv, (rssid,))

    def truncate_rss_history(self) -> None:
        from app.helper import RssHelper

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


class RssParserEngine:
    """RSS 解析引擎：纯逻辑，无状态，负责 XML/JSON 报文解析"""

    @staticmethod
    def parse_items(rss_parser: dict, rss_text: str, address_index: int) -> list[dict[str, Any]]:
        """
        根据解析器配置解析 RSS 原始文本
        :param rss_parser: 解析器配置字典
        :param rss_text: HTTP 响应文本
        :param address_index: 地址序号（用于回显）
        :return: 解析后的条目列表
        """
        parser_type = rss_parser.get("type")
        parser_format = json.loads(rss_parser.get("format") or "{}")
        rss_result: list[dict[str, Any]] = []

        if parser_type == "XML":
            try:
                result_tree = etree.XML(rss_text.encode("utf-8"))
                item_list = result_tree.xpath(parser_format.get("list")) or []
                for item in item_list:
                    rss_item = {}
                    for key, attr in parser_format.get("item", {}).items():
                        if attr.get("path"):
                            if attr.get("namespaces"):
                                value = item.xpath(
                                    "//ns:{}".format(attr.get("path")), namespaces={"ns": attr.get("namespaces")}
                                )
                            else:
                                value = item.xpath(attr.get("path"))
                        elif attr.get("value"):
                            value = attr.get("value")
                        else:
                            continue
                        if value:
                            rss_item.update({key: value[0]})
                    rss_item.update({"address_index": address_index})
                    rss_result.append(rss_item)
            except Exception as err:
                raise ValueError(f"XML解析失败: {str(err)}") from err

        elif parser_type == "JSON":
            try:
                result_json = json.loads(rss_text)
            except Exception as err:
                raise ValueError(f"JSON解析失败: {str(err)}") from err
            item_list = jsonpath.jsonpath(result_json, parser_format.get("list"))
            if not item_list or not isinstance(item_list, list):
                raise ValueError("jsonpath结果不是列表")
            item_list = item_list[0]
            if not isinstance(item_list, list):
                raise ValueError("list后不是列表")
            for item in item_list:
                rss_item = {}
                for key, attr in parser_format.get("item", {}).items():
                    if attr.get("path"):
                        value = jsonpath.jsonpath(item, attr.get("path"))
                    elif attr.get("value"):
                        value = attr.get("value")
                    else:
                        continue
                    if value:
                        rss_item.update({key: value[0]})
                rss_item.update({"address_index": address_index})
                rss_result.append(rss_item)

        return rss_result


class RssTaskService(metaclass=SingletonMeta):
    """RSS 任务服务：负责任务加载、调度管理、报文处理"""

    message: Message
    searcher: Searcher
    filter: Filter
    media: MediaService
    filterrule: Any
    downloader: Downloader
    subscribe: Subscribe
    config_repo: UserRssConfigRepositoryAdapter
    rss_repo: RssHistoryRepositoryAdapter
    rsshelper: RssHelper

    _jobstore = "rsscheck"
    _rss_tasks: list[dict[str, Any]] = []
    _rss_parsers: list[dict[str, Any]] = []
    _site_users = {"D": "下载", "R": "订阅", "S": "搜索"}

    def __init__(
        self,
        config_repo: Any | None = None,
        rss_repo: Any | None = None,
        rsshelper: Any | None = None,
        message: Any | None = None,
        searcher: Any | None = None,
        filter_: Any | None = None,
        media: Any | None = None,
        downloader: Any | None = None,
        subscribe: Any | None = None,
    ):
        self.config_repo = config_repo or UserRssConfigRepositoryAdapter()
        self.rss_repo = rss_repo or RssHistoryRepositoryAdapter()
        self.rsshelper = rsshelper or RssHelper()
        self.message = message or Message()
        self.searcher = searcher or Searcher()
        self.filter = filter_ or Filter()
        self.media = media or MediaService()
        self.downloader = downloader or Downloader()
        self.subscribe = subscribe or Subscribe()

    def init_config(self) -> None:
        # 移除现有任务
        self.stop_service()
        # 读取解析器列表
        rss_parsers = self.config_repo.get_userrss_parser()
        self._rss_parsers = []
        for rss_parser in rss_parsers:
            self._rss_parsers.append(
                {
                    "id": rss_parser.ID,
                    "name": rss_parser.NAME,
                    "type": rss_parser.TYPE,
                    "format": rss_parser.FORMAT,
                    "params": rss_parser.PARAMS,
                    "note": rss_parser.NOTE,
                }
            )
        # 读取任务任务列表
        rsstasks = self.config_repo.get_userrss_tasks()
        self._rss_tasks = []
        for task in rsstasks:
            if task.FILTER:
                filterrule = self.filter.get_rule_groups(groupid=task.FILTER)
            else:
                filterrule = {}
            # 解析属性
            note = {}
            if task.NOTE:
                try:
                    note = json.loads(task.NOTE)
                except Exception as e:
                    print(str(e))
                    note = {}
            save_path = note.get("save_path") or ""
            recognization = note.get("recognization") or "Y"
            proxy = note.get("proxy") in ["Y", "1", True]
            try:
                addresses = json.loads(task.ADDRESS)
                if not isinstance(addresses, list):
                    addresses = [addresses]
            except Exception as e:
                print(str(e))
                addresses = [task.ADDRESS]
            try:
                parsers = json.loads(task.PARSER)
                if not isinstance(parsers, list):
                    parsers = [task.PARSER]
            except Exception as e:
                print(str(e))
                parsers = [task.PARSER]
            state = task.STATE in ["Y", "1", True]
            self._rss_tasks.append(
                {
                    "id": task.ID,
                    "name": task.NAME,
                    "address": addresses,
                    "proxy": proxy,
                    "parser": parsers,
                    "interval": task.INTERVAL,
                    "uses": task.USES if task.USES != "S" else "R",
                    "uses_text": self._site_users.get(task.USES),
                    "include": task.INCLUDE,
                    "exclude": task.EXCLUDE,
                    "filter": task.FILTER,
                    "filter_name": filterrule.get("name") if filterrule else "",
                    "update_time": task.UPDATE_TIME,
                    "counter": task.PROCESS_COUNT,
                    "state": state,
                    "save_path": task.SAVE_PATH or save_path,
                    "download_setting": task.DOWNLOAD_SETTING or "",
                    "recognization": task.RECOGNIZATION or recognization,
                    "over_edition": task.OVER_EDITION or 0,
                    "sites": json.loads(task.SITES) if task.SITES else {"rss_sites": [], "search_sites": []},
                    "filter_args": json.loads(task.FILTER_ARGS)
                    if task.FILTER_ARGS
                    else {"restype": "", "pix": "", "team": ""},
                }
            )
        if not self._rss_tasks:
            return
        # 启动RSS任务
        rss_flag = False
        for task in self._rss_tasks:
            if task.get("state") and task.get("interval"):
                cron = str(task.get("interval")).strip()
                job_id = f"RssTaskService.check_task_rss_{task.get('id')}"
                if cron.isdigit():
                    # 分钟
                    rss_flag = True
                    SchedulerCore().start_job(
                        {
                            "func": self.check_task_rss,
                            "name": f"自定义订阅任务 {task.get('name')}",
                            "args": (task.get("id"),),
                            "job_id": job_id,
                            "trigger": "interval",
                            "seconds": int(cron) * 60,
                            "jobstore": self._jobstore,
                        }
                    )
                elif cron.count(" ") == 4:
                    # cron表达式
                    try:
                        SchedulerCore().start_job(
                            {
                                "func": self.check_task_rss,
                                "name": f"自定义订阅任务 {task.get('name')}",
                                "args": (task.get("id"),),
                                "job_id": job_id,
                                "trigger": "cron",
                                "cron": cron,
                                "jobstore": self._jobstore,
                            }
                        )
                        rss_flag = True
                    except Exception as e:
                        log.info("{} 自定义订阅cron表达式 配置格式错误：{} {}".format(task.get("name"), cron, str(e)))
        if rss_flag:
            SchedulerCore().print_jobs(jobstore=self._jobstore)
            log.info("自定义订阅服务启动")

    def get_rsstask_info(self, taskid: int | str | None = None) -> Any:
        """
        获取单个RSS任务详细信息
        """
        if taskid:
            if str(taskid).isdigit():
                taskid = int(taskid)
                for task in self._rss_tasks:
                    if task.get("id") == taskid:
                        return task
            else:
                return {}
        return self._rss_tasks

    def check_task_rss(self, taskid: int | None) -> None:
        """
        处理自定义RSS任务，由定时服务调用
        :param taskid: 自定义RSS的ID
        """
        if not taskid:
            return
        # 需要下载的项目
        rss_download_torrents = []
        # 需要订阅的项目
        rss_subscribe_torrents = []
        # 需要搜索的项目
        rss_search_torrents = []
        # 任务信息
        taskinfo = self.get_rsstask_info(taskid)
        if not taskinfo:
            return
        rss_result = self.__parse_userrss_result(taskinfo)
        if len(rss_result) == 0:
            log.warn("【RssTaskService】{} 未下载到数据".format(taskinfo.get("name")))
            return
        else:
            log.info("【RssTaskService】{} 获取数据：{}".format(taskinfo.get("name"), len(rss_result)))
        # 处理RSS结果
        res_num = 0
        no_exists = {}
        for res in rss_result:
            try:
                # 种子名
                title = res.get("title")
                if not title:
                    continue
                # 种子链接
                enclosure = res.get("enclosure")
                # 种子页面
                page_url = res.get("link")
                # 种子大小
                size = StringUtils.str_filesize(res.get("size"))
                # 年份
                year = res.get("year")
                if year and len(year) > 4:
                    year = year[:4]
                # 类型
                mediatype = res.get("type")
                if mediatype:
                    mediatype = MediaType.MOVIE if mediatype == "movie" else MediaType.TV

                log.info(f"【RssTaskService】开始处理：{title}")

                task_type = taskinfo.get("uses")
                meta_name = f"{title} {year}" if year else title
                # 检查是否已处理过
                if self.is_article_processed(task_type, title, year, enclosure):
                    log.info(f"【RssTaskService】{title} 已处理过")
                    continue

                if task_type == "D":
                    media_info = meta_info(title=meta_name, mtype=mediatype)
                    if taskinfo.get("recognization") == "Y":
                        media_info = self.media.get_media_info(title=meta_name, mtype=mediatype)
                        if not media_info:
                            log.warn(f"【RssTaskService】{title} 识别媒体信息出错！")
                            continue
                        if not media_info.tmdb_info:
                            log.info(f"【RssTaskService】{title} 识别为 {media_info.get_name()} 未匹配到媒体信息")
                            continue
                        # 检查是否已存在
                        if media_info.type == MediaType.MOVIE:
                            exist_flag, no_exists, _ = self.downloader.check_exists_medias(
                                meta_info=media_info, no_exists=no_exists
                            )
                            if exist_flag:
                                log.info(f"【RssTaskService】电影 {media_info.get_title_string()} 已存在")
                                continue
                        else:
                            exist_flag, no_exists, _ = self.downloader.check_exists_medias(
                                meta_info=media_info, no_exists=no_exists
                            )
                            # 当前剧集已存在，跳过
                            if exist_flag:
                                # 已全部存在
                                if not no_exists or not no_exists.get(media_info.tmdb_id):
                                    log.info(
                                        f"【RssTaskService】电视剧 {media_info.get_title_string()} {media_info.get_season_episode_string()} 已存在"
                                    )
                                continue
                            if no_exists.get(media_info.tmdb_id):
                                log.info(
                                    f"【RssTaskService】{media_info.get_title_string()} 缺失季集：{no_exists.get(media_info.tmdb_id)}"
                                )
                    # 大小及种子页面
                    media_info.set_torrent_info(
                        size=size, page_url=page_url, site=taskinfo.get("name"), enclosure=enclosure
                    )
                    # 检查种子是否匹配过滤条件
                    filter_args = {
                        "include": taskinfo.get("include"),
                        "exclude": taskinfo.get("exclude"),
                        "rule": taskinfo.get("filter"),
                    }
                    match_flag, res_order, match_msg = self.filter.check_torrent_filter(
                        meta_info=media_info, filter_args=filter_args
                    )
                    # 未匹配
                    if not match_flag:
                        log.info(f"【RssTaskService】{match_msg}")
                        continue
                    else:
                        # 匹配优先级
                        media_info.set_torrent_info(res_order=res_order)
                        if taskinfo.get("recognization") == "Y":
                            log.info(
                                f"【RssTaskService】{title} 识别为 {media_info.get_title_string()} {media_info.get_season_episode_string()} 匹配成功"
                            )
                            # 补充TMDB完整信息
                            if not media_info.tmdb_info:
                                media_info.set_tmdb_info(
                                    self.media.get_tmdb_info(mtype=media_info.type, tmdbid=media_info.tmdb_id)
                                )
                            # TMDB信息插入订阅任务
                            if media_info.type != MediaType.MOVIE:
                                self.config_repo.insert_userrss_mediainfos(taskid, media_info)
                        else:
                            log.info(f"【RssTaskService】{title}  匹配成功")
                    # 添加下载列表
                    if not enclosure:
                        log.warn("【RssTaskService】{} RSS报文中没有enclosure种子链接".format(taskinfo.get("name")))
                        continue
                    if media_info not in rss_download_torrents:
                        rss_download_torrents.append(media_info)
                        res_num = res_num + 1
                elif task_type == "R":
                    # 识别种子名称，开始搜索TMDB
                    media_info = meta_info(title=meta_name, mtype=mediatype)
                    # 检查种子是否匹配过滤条件
                    filter_args = {"include": taskinfo.get("include"), "exclude": taskinfo.get("exclude"), "rule": -1}
                    match_flag, _, match_msg = self.filter.check_torrent_filter(
                        meta_info=media_info, filter_args=filter_args
                    )
                    # 未匹配
                    if not match_flag:
                        log.info(f"【RssTaskService】{match_msg}")
                        continue
                    # 检查是否已订阅过
                    if self.rss_repo.check_rss_history(
                        type_str="MOV" if media_info.type == MediaType.MOVIE else "TV",
                        name=media_info.title,
                        year=media_info.year,
                        season=media_info.get_season_string(),
                    ):
                        log.info(
                            f"【RssTaskService】{media_info.get_title_string()}{media_info.get_season_string()} 已订阅过"
                        )
                        continue
                    # 订阅meta_name存enclosure与下载区别
                    media_info.set_torrent_info(enclosure=meta_name)
                    # 添加处理历史
                    self.rsshelper.insert_rss_torrents(media_info)
                    if media_info not in rss_subscribe_torrents:
                        rss_subscribe_torrents.append(media_info)
                        res_num = res_num + 1
                else:
                    continue
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
                log.error(f"【RssTaskService】处理RSS发生错误：{str(e)} - {traceback.format_exc()}")
                continue
        log.info("【RssTaskService】{} 处理结束，匹配到 {} 个有效资源".format(taskinfo.get("name"), res_num))
        # 添加下载
        if rss_download_torrents:
            for media in rss_download_torrents:
                downloader_id, ret, ret_msg = self.downloader.download(
                    media_info=media,
                    download_dir=taskinfo.get("save_path"),
                    download_setting=taskinfo.get("download_setting"),
                    in_from=SearchType.USERRSS,
                    proxy=taskinfo.get("proxy"),
                )
                if ret:
                    # 下载类型的 这里下载成功了 插入数据库
                    self.rsshelper.insert_rss_torrents(media)
                    # 登记自定义RSS任务下载记录
                    conf = self.downloader.get_downloader_conf(downloader_id)
                    downloader_name = conf.get("name") if conf else ""
                    self.config_repo.insert_userrss_task_history(taskid, media.org_string, downloader_name)
                else:
                    log.error(
                        "【RssTaskService】添加下载任务 {} 失败：{}".format(media.get_title_string(), ret_msg or "请检查下载任务是否已存在")
                    )
        # 添加订阅
        if rss_subscribe_torrents:
            for media in rss_subscribe_torrents:
                code, msg, rss_media = self.subscribe.add_rss_subscribe(
                    mtype=media.type,
                    name=media.get_name(),
                    year=media.year,
                    channel=RssType.Manual,
                    season=media.begin_season,
                    rss_sites=taskinfo.get("sites", {}).get("rss_sites"),
                    search_sites=taskinfo.get("sites", {}).get("search_sites"),
                    over_edition=bool(taskinfo.get("over_edition")),
                    filter_restype=taskinfo.get("filter_args", {}).get("restype"),
                    filter_pix=taskinfo.get("filter_args", {}).get("pix"),
                    filter_team=taskinfo.get("filter_args", {}).get("team"),
                    filter_rule=taskinfo.get("filter"),
                    save_path=taskinfo.get("save_path"),
                    download_setting=taskinfo.get("download_setting"),
                    in_from=SearchType.USERRSS,
                )
                if not rss_media or code != 0:
                    log.warn(f"【RssTaskService】{media.get_name()} 添加订阅失败：{msg}")

        # 更新状态
        counter = len(rss_download_torrents) + len(rss_subscribe_torrents) + len(rss_search_torrents)
        if counter:
            self.config_repo.update_userrss_task_info(taskid, counter)
            taskinfo["counter"] = (
                int(taskinfo.get("counter")) + counter if str(taskinfo.get("counter")).isdigit() else counter
            )
            taskinfo["update_time"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time()))

    def __parse_userrss_result(self, taskinfo):
        """
        获取RSS链接数据，根据PARSER进行解析获取返回结果
        """
        task_name = taskinfo.get("name")
        rss_urls = taskinfo.get("address")
        rss_parsers = taskinfo.get("parser")
        count = min(len(rss_urls), len(rss_parsers))
        rss_result = []
        for i in range(count):
            rss_url = rss_urls[i]
            if not rss_url:
                continue
            # 检查解析器有效性
            rss_parser = self.get_userrss_parser(rss_parsers[i])
            if not rss_parser:
                log.error(f"【RssTaskService】任务 {task_name} RSS地址 {rss_url} 配置解析器不存在")
                continue
            parser_name = rss_parser.get("name")
            if not rss_parser.get("format"):
                log.error(f"【RssTaskService】任务 {task_name} 配置解析器 {parser_name} 格式不正确")
                continue
            try:
                json.loads(rss_parser.get("format"))
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
                log.error(f"【RssTaskService】任务 {task_name} 配置解析器 {parser_name} 不是合法的Json格式")
                continue

            # 拼装链接
            if rss_parser.get("params"):
                _dict = {"TMDBKEY": Config().get_config("app").get("rmt_tmdbkey")}
                try:
                    param_url = rss_parser.get("params").format(**_dict)
                except Exception as e:
                    ExceptionUtils.exception_traceback(e)
                    log.error(f"【RssTaskService】任务 {task_name} 配置解析器 {parser_name} 附加参数不合法")
                    continue
                rss_url = f"{rss_url}?{param_url}" if rss_url.find("?") == -1 else f"{rss_url}&{param_url}"
            # 请求数据
            try:
                ret = RequestUtils(proxies=get_proxies() if taskinfo.get("proxy") else None).get_res(rss_url)
                if not ret:
                    continue
                ret.encoding = ret.apparent_encoding
            except Exception as e2:
                ExceptionUtils.exception_traceback(e2)
                continue
            # 解析数据
            try:
                items = RssParserEngine.parse_items(rss_parser, ret.text, i + 1)
                rss_result.extend(items)
            except Exception as err:
                ExceptionUtils.exception_traceback(err)
                log.error(f"【RssTaskService】任务 {task_name} RSS地址 {rss_url} 获取的订阅报文无法解析：{str(err)}")
                continue
        return rss_result

    def get_userrss_parser(self, pid: int | str | None = None) -> Any:
        if pid:
            for rss_parser in self._rss_parsers:
                if rss_parser.get("id") == int(pid):
                    return rss_parser
            return {}
        else:
            return self._rss_parsers

    def get_rss_articles(self, taskid: int | None) -> Any:
        """
        查看自定义RSS报文
        :param taskid: 自定义RSS的ID
        """
        if not taskid:
            return
        # 下载订阅的文章列表
        rss_articles = []
        # 任务信息
        taskinfo = self.get_rsstask_info(taskid)
        if not taskinfo:
            return
        rss_result = self.__parse_userrss_result(taskinfo)
        if len(rss_result) == 0:
            return []
        for res in rss_result:
            try:
                # 种子名
                title = res.get("title")
                if not title:
                    continue
                # 种子链接
                enclosure = res.get("enclosure")
                # 种子页面
                link = res.get("link")
                # 副标题
                description = res.get("description")
                # 种子大小
                size = StringUtils.str_filesize(res.get("size"))
                # 发布日期
                date = StringUtils.unify_datetime_str(res.get("date")) or ""
                # 年份
                year = res.get("year")
                if year and len(year) > 4:
                    year = year[:4]
                # 检查是不是处理过
                finish_flag = self.is_article_processed(taskinfo.get("uses"), title, year, enclosure)
                # 信息聚合
                params = {
                    "title": title,
                    "link": link,
                    "enclosure": enclosure,
                    "size": size,
                    "description": description,
                    "date": date,
                    "finish_flag": finish_flag,
                    "year": year,
                    "address_index": res.get("address_index"),
                }
                if params not in rss_articles:
                    rss_articles.append(params)
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
                log.error(f"【RssTaskService】获取RSS报文发生错误：{str(e)} - {traceback.format_exc()}")
        return sorted(rss_articles, key=lambda x: x["date"], reverse=True)

    def test_rss_articles(self, taskid: int | None, title: str) -> tuple[Any, bool, bool] | None:
        """
        测试RSS报文
        :param taskid: 自定义RSS的ID
        :param title: RSS报文title
        """
        # 任务信息
        taskinfo = self.get_rsstask_info(taskid)
        if not taskinfo:
            return
        # 识别种子名称，开始搜索TMDB

        media_info = self.media.get_media_info(title=title)
        if not media_info:
            log.warn(f"【RssTaskService】{title} 识别媒体信息出错！")
            return None
        # 检查是否匹配
        filter_args = {
            "include": taskinfo.get("include"),
            "exclude": taskinfo.get("exclude"),
            "rule": taskinfo.get("filter") if taskinfo.get("uses") == "D" else None,
        }
        match_flag, res_order, match_msg = self.filter.check_torrent_filter(
            meta_info=media_info, filter_args=filter_args
        )
        # 未匹配
        if not match_flag:
            log.info(f"【RssTaskService】{match_msg}")
        else:
            log.info(
                f"【RssTaskService】{title} 识别为 {media_info.get_title_string()} {media_info.get_season_episode_string()} 匹配成功"
            )
        media_info.set_torrent_info(res_order=res_order)
        # 检查是否已存在
        no_exists = {}
        exist_flag = False
        if not media_info.tmdb_id:
            log.info(f"【RssTaskService】{title} 识别为 {media_info.get_name()} 未匹配到媒体信息")
        else:
            if media_info.type == MediaType.MOVIE:
                exist_flag, no_exists, _ = self.downloader.check_exists_medias(
                    meta_info=media_info, no_exists=no_exists
                )
                if exist_flag:
                    log.info(f"【RssTaskService】电影 {media_info.get_title_string()} 已存在")
            else:
                exist_flag, no_exists, _ = self.downloader.check_exists_medias(
                    meta_info=media_info, no_exists=no_exists
                )
                if exist_flag:
                    # 已全部存在
                    if not no_exists or not no_exists.get(media_info.tmdb_id):
                        log.info(
                            f"【RssTaskService】电视剧 {media_info.get_title_string()} {media_info.get_season_episode_string()} 已存在"
                        )
                if no_exists.get(media_info.tmdb_id):
                    log.info(
                        f"【RssTaskService】{media_info.get_title_string()} 缺失季集：{no_exists.get(media_info.tmdb_id)}"
                    )
        return media_info, match_flag, exist_flag

    def check_rss_articles(self, taskid: int | None, flag: str, articles: list[dict]) -> bool:
        """
        RSS报文处理设置
        :param taskid: 自定义RSS的ID
        :param flag: set_finished/set_unfinish
        :param articles: 报文(title/enclosure)
        """
        try:
            task_type = self.get_rsstask_info(taskid).get("uses")
            if flag == "set_finished":
                for article in articles:
                    title = article.get("title")
                    enclosure = article.get("enclosure")
                    year = article.get("year")
                    meta_name = f"{title} {year}" if year else title
                    if not self.is_article_processed(task_type, title, enclosure, year):
                        if task_type == "D":
                            self.rsshelper.simple_insert_rss_torrents(meta_name, enclosure)
                        elif task_type == "R":
                            self.rsshelper.simple_insert_rss_torrents(meta_name, meta_name)
            elif flag == "set_unfinish":
                for article in articles:
                    title = article.get("title")
                    enclosure = article.get("enclosure")
                    year = article.get("year")
                    meta_name = f"{title} {year}" if year else title
                    if task_type == "D":
                        self.rsshelper.simple_delete_rss_torrents(meta_name, enclosure)
                    elif task_type == "R":
                        self.rsshelper.simple_delete_rss_torrents(meta_name, meta_name)
            else:
                return False
            return True
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            log.error(f"【RssTaskService】设置RSS报文状态时发生错误：{str(e)} - {traceback.format_exc()}")
            return False

    def download_rss_articles(self, taskid: int | None, articles: list[dict]) -> bool | None:
        """
        RSS报文下载
        :param taskid: 自定义RSS的ID
        :param articles: 报文(title/enclosure)
        """
        if not taskid:
            return
        # 任务信息
        taskinfo = self.get_rsstask_info(taskid)
        if not taskinfo:
            return
        for article in articles:
            media = self.media.get_media_info(title=article.get("title"))
            if not media:
                log.warn(f"【RssTaskService】{article.get('title')} 识别媒体信息出错！")
                continue
            media.set_torrent_info(enclosure=article.get("enclosure"))
            downloader_id, ret, ret_msg = self.downloader.download(
                media_info=media,
                download_dir=taskinfo.get("save_path"),
                download_setting=taskinfo.get("download_setting"),
                in_from=SearchType.USERRSS,
                proxy=taskinfo.get("proxy"),
            )
            conf = self.downloader.get_downloader_conf(downloader_id)
            downloader_name = conf.get("name") if conf else ""
            if ret:
                # 插入数据库
                self.rsshelper.insert_rss_torrents(media)
                # 登记自定义RSS任务下载记录
                self.config_repo.insert_userrss_task_history(taskid, media.org_string, downloader_name)
            else:
                log.error(
                    "【RssTaskService】添加下载任务 {} 失败：{}".format(media.get_title_string(), ret_msg or "请检查下载任务是否已存在")
                )
                return False
        return True

    def get_userrss_mediainfos(self) -> list[dict]:
        taskinfos = self.config_repo.get_userrss_tasks()
        mediainfos_all = []
        for taskinfo in taskinfos:
            mediainfos = json.loads(taskinfo.MEDIAINFOS) if taskinfo.MEDIAINFOS else []
            if mediainfos:
                mediainfos_all += mediainfos
        return mediainfos_all

    def stop_service(self) -> None:
        """
        停止服务
        """
        try:
            SchedulerCore().remove_all_jobs(jobstore=self._jobstore)
        except Exception as e:
            print(str(e))

    def is_article_processed(self, task_type: str, title: str, year: str | None, enclosure: str | None) -> bool:
        """
        检查报文是否已处理
        :param task_type: 订阅任务类型
        :param title: 报文标题
        :param year: 报文年份
        :param enclosure: 报文链接
        :return:
        """
        meta_name = f"{title} {year}" if year else title
        match task_type:
            case "D":
                return self.rsshelper.is_rssd_by_simple(meta_name, enclosure)
            case "R":
                return self.rsshelper.is_rssd_by_simple(meta_name, meta_name)
            case _:
                return False

    def delete_userrss_task(self, tid: int | None) -> Any:
        """
        删除自定义RSS任务
        :param tid: 任务ID
        """
        ret = self.config_repo.delete_userrss_task(tid)
        self.init_config()
        return ret

    def update_userrss_task(self, item: dict) -> Any:
        """
        更新自定义RSS任务
        :param item: 任务信息
        """
        ret = self.config_repo.update_userrss_task(item)
        self.init_config()
        return ret

    def check_userrss_task(self, tid: int | None = None, state: str | None = None) -> Any:
        """
        设置自定义RSS任务
        :param tid: 任务ID
        :param state: 任务状态
        """
        ret = self.config_repo.check_userrss_task(tid, state)
        self.init_config()
        return ret

    def delete_userrss_parser(self, pid: int | None) -> Any:
        """
        删除自定义RSS解析器
        :param pid: 解析器ID
        """
        ret = self.config_repo.delete_userrss_parser(pid)
        self.init_config()
        return ret

    def update_userrss_parser(self, item: dict) -> Any:
        """
        更新自定义RSS解析器
        :param item: 解析器信息
        """
        ret = self.config_repo.update_userrss_parser(item)
        self.init_config()
        return ret

    def get_userrss_task_history(self, task_id: int | None) -> Any:
        """
        获取自定义RSS任务下载记录
        :param task_id: 任务ID
        """
        return self.config_repo.get_userrss_task_history(task_id)

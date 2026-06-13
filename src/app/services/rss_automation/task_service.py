"""RSS 任务服务 Facade."""

import json
from typing import Any, cast

import log
from app.core.exceptions import RepositoryError, ServiceError
from app.db.repositories.config_repo_adapter import UserRssConfigRepositoryAdapter
from app.db.repositories.subscribe_repo_adapter import SubscribeHistoryRepositoryAdapter
from app.events.bus import EventBus
from app.media import MediaService
from app.message import Message
from app.services.downloader_core import DownloaderCore as Downloader
from app.services.filter_service import FilterService as Filter
from app.services.rss_automation.articles import (
    _check_rss_articles,
    _download_rss_articles,
    _get_rss_articles,
    _test_rss_articles,
)
from app.services.rss_automation.executor import _check_task_rss
from app.services.rss_processor import RssHelper
from app.services.search_service import Searcher
from app.sites.engine import SiteEngine


class RssTaskService:
    """RSS 任务服务：负责任务加载、调度管理、报文处理"""

    message: Message
    searcher: Searcher
    filter: Filter
    media: MediaService
    filterrule: Any
    downloader: Downloader
    config_repo: UserRssConfigRepositoryAdapter
    rss_repo: SubscribeHistoryRepositoryAdapter
    rsshelper: RssHelper
    event_bus: EventBus | None
    site_engine: SiteEngine

    _jobstore = "rsscheck"
    _rss_tasks: list[dict[str, Any]] = []
    _rss_parsers: list[dict[str, Any]] = []
    _site_users = {"D": "下载", "R": "订阅", "S": "搜索"}

    def __init__(
        self,
        config_repo: Any,
        rss_repo: Any,
        rsshelper: Any,
        message: Any,
        searcher: Any,
        filter_: Any,
        media: Any,
        downloader: Any,
        scheduler_core: Any,
        site_engine: SiteEngine,
        event_bus: EventBus | None = None,
    ):
        self.config_repo = config_repo
        self.rss_repo = rss_repo
        self.rsshelper = rsshelper
        self.message = message
        self.searcher = searcher
        self.filter = filter_
        self.media = media
        self.downloader = downloader
        self._scheduler_core = scheduler_core
        self.site_engine = site_engine
        self.event_bus = event_bus

    def _refresh(self) -> None:
        # 移除现有任务
        self.stop_service()
        # 读取解析器列表
        _raw = self.config_repo.get_userrss_parser()
        rss_parsers = cast(list[Any], _raw) if _raw else []
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
            task_filter_id = int(str(task.FILTER or 0))
            if task_filter_id:
                filterrule = self.filter.get_rule_groups(groupid=task_filter_id)
            else:
                filterrule = {}
            # 解析属性
            note = {}
            task_note = str(task.NOTE or "")
            if task_note:
                try:
                    note = json.loads(task_note)
                except (ServiceError, RepositoryError):
                    raise
                except Exception as e:
                    print(str(e))
                    note = {}
            save_path = note.get("save_path") or ""
            recognization = note.get("recognization") or "Y"
            proxy = note.get("proxy") in ["Y", "1", True]
            try:
                addresses = json.loads(str(task.ADDRESS))
                if not isinstance(addresses, list):
                    addresses = [addresses]
            except (ServiceError, RepositoryError):
                raise
            except Exception as e:
                print(str(e))
                addresses = [task.ADDRESS]
            try:
                parsers = json.loads(str(task.PARSER))
                if not isinstance(parsers, list):
                    parsers = [task.PARSER]
            except (ServiceError, RepositoryError):
                raise
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
                    "uses": task.USES if str(task.USES or "") != "S" else "R",
                    "uses_text": self._site_users.get(str(task.USES)),
                    "include": task.INCLUDE,
                    "exclude": task.EXCLUDE,
                    "filter": task.FILTER,
                    "filter_name": filterrule.get("name") if isinstance(filterrule, dict) else "",
                    "update_time": task.UPDATE_TIME,
                    "counter": task.PROCESS_COUNT,
                    "state": state,
                    "save_path": task.SAVE_PATH or save_path,
                    "download_setting": task.DOWNLOAD_SETTING or "",
                    "recognization": task.RECOGNIZATION or recognization,
                    "over_edition": task.OVER_EDITION or 0,
                    "sites": json.loads(str(task.SITES or ""))
                    if str(task.SITES or "")
                    else {"rss_sites": [], "search_sites": []},
                    "filter_args": json.loads(str(task.FILTER_ARGS or ""))
                    if str(task.FILTER_ARGS or "")
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
                    self._scheduler_core.start_job(
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
                        self._scheduler_core.start_job(
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
                    except (ServiceError, RepositoryError):
                        raise
                    except Exception as e:
                        log.info("{} 自定义订阅cron表达式 配置格式错误：{} {}".format(task.get("name"), cron, str(e)))
        if rss_flag:
            self._scheduler_core.print_jobs(jobstore=self._jobstore)
            log.info("自定义订阅服务启动")

    def get_rsstask_info(self, taskid: int | str | None = None) -> Any:
        """获取单个RSS任务详细信息"""
        if taskid:
            if str(taskid).isdigit():
                taskid = int(taskid)
                for task in self._rss_tasks:
                    if task.get("id") == taskid:
                        return task
            else:
                return {}
        return self._rss_tasks

    def get_userrss_parser(self, pid: int | str | None = None) -> Any:
        if pid:
            for rss_parser in self._rss_parsers:
                if rss_parser.get("id") == int(pid):
                    return rss_parser
            return {}
        else:
            return self._rss_parsers

    def get_userrss_mediainfos(self) -> list[dict]:
        taskinfos = self.config_repo.get_userrss_tasks()
        mediainfos_all = []
        for taskinfo in taskinfos:
            mediainfos_raw = str(taskinfo.MEDIAINFOS or "")
            mediainfos = json.loads(mediainfos_raw) if mediainfos_raw else []
            if mediainfos:
                mediainfos_all += mediainfos
        return mediainfos_all

    def stop_service(self) -> None:
        """停止服务"""
        try:
            self._scheduler_core.remove_all_jobs(jobstore=self._jobstore)
        except (ServiceError, RepositoryError):
            raise
        except Exception as e:
            print(str(e))

    def is_article_processed(self, task_type: str, title: str, year: str | None, enclosure: str | None) -> bool:
        """检查报文是否已处理"""
        meta_name = f"{title} {year}" if year else title
        match task_type:
            case "D":
                return self.rsshelper.is_rssd_by_simple(meta_name, enclosure)
            case "R":
                return self.rsshelper.is_rssd_by_simple(meta_name, meta_name)
            case _:
                return False

    def delete_userrss_task(self, tid: int | None) -> Any:
        """删除自定义RSS任务"""
        ret = self.config_repo.delete_userrss_task(tid)
        self._refresh()
        return ret

    def update_userrss_task(self, item: dict) -> Any:
        """更新自定义RSS任务"""
        ret = self.config_repo.update_userrss_task(item)
        self._refresh()
        return ret

    def check_userrss_task(self, tid: int | None = None, state: str | None = None) -> Any:
        """设置自定义RSS任务"""
        ret = self.config_repo.check_userrss_task(tid, state)
        self._refresh()
        return ret

    def delete_userrss_parser(self, pid: int | None) -> Any:
        """删除自定义RSS解析器"""
        ret = self.config_repo.delete_userrss_parser(pid)
        self._refresh()
        return ret

    def update_userrss_parser(self, item: dict) -> Any:
        """更新自定义RSS解析器"""
        ret = self.config_repo.update_userrss_parser(item)
        self._refresh()
        return ret

    def get_userrss_task_history(self, task_id: int | None) -> Any:
        """获取自定义RSS任务下载记录"""
        return self.config_repo.get_userrss_task_history(task_id or 0)

    def check_task_rss(self, taskid: int | None) -> None:
        """处理自定义RSS任务，由定时服务调用"""
        return _check_task_rss(self, taskid, event_bus=self.event_bus)

    def get_rss_articles(self, taskid: int | None) -> Any:
        """查看自定义RSS报文"""
        return _get_rss_articles(self, taskid)

    def test_rss_articles(self, taskid: int | None, title: str) -> tuple[Any, bool, bool] | None:
        """测试RSS报文"""
        return _test_rss_articles(self, taskid, title)

    def check_rss_articles(self, taskid: int | None, flag: str, articles: list[dict]) -> bool:
        """RSS报文处理设置"""
        return _check_rss_articles(self, taskid, flag, articles)

    def download_rss_articles(self, taskid: int | None, articles: list[dict]) -> bool | None:
        """RSS报文下载"""
        return _download_rss_articles(self, taskid, articles)

# -*- coding: utf-8 -*-
from typing import Any, Dict, List, Optional

from app.schemas.userrss import (
    UserRssArticleListDTO,
    UserRssHistoryDTO,
    UserRssArticleTestDTO,
    UserRssTaskUpdateDTO,
)
from app.services.rss_service import RssTaskService as RssChecker
from web.core.action_utils import mediainfo_dict


class UserRssService:
    """自定义RSS任务服务：封装参数转换与数据格式化"""

    def __init__(self, rss_checker: Optional[RssChecker] = None):
        self._checker = rss_checker or RssChecker()

    def check_tasks(self, taskids: Optional[list], flag: str) -> None:
        flag_dict = {"enable": True, "disable": False}
        state = flag_dict.get(flag)
        if state is not None:
            if taskids:
                for taskid in taskids:
                    self._checker.check_userrss_task(tid=taskid, state=state)
            else:
                self._checker.check_userrss_task(state=state)

    def delete_parser(self, pid) -> Optional[bool]:
        return self._checker.delete_userrss_parser(pid)

    def delete_task(self, tid) -> Optional[bool]:
        return self._checker.delete_userrss_task(tid)

    def get_parsers(self):
        return self._checker.get_userrss_parser()

    def get_parser(self, pid):
        return self._checker.get_userrss_parser(pid=pid)

    def get_task(self, taskid):
        return self._checker.get_rsstask_info(taskid=taskid)

    def get_tasks(self):
        return self._checker.get_rsstask_info()

    def get_articles(self, taskid) -> UserRssArticleListDTO:
        task_info: Any = self._checker.get_rsstask_info(taskid=taskid)
        uses = task_info.get("uses") if isinstance(task_info, dict) else None
        address_count = len(task_info.get("address", [])) if isinstance(task_info, dict) else 0
        articles = self._checker.get_rss_articles(taskid)
        return UserRssArticleListDTO(
            articles=articles or [],
            count=len(articles) if articles else 0,
            uses=uses,
            address_count=address_count
        )

    def get_history(self, taskid) -> UserRssHistoryDTO:
        historys = self._checker.get_userrss_task_history(task_id=taskid)
        downloads = []
        for history in historys:
            downloads.append({
                "title": history.TITLE,
                "downloader": history.DOWNLOADER,
                "date": history.DATE
            })
        return UserRssHistoryDTO(
            downloads=downloads,
            count=len(downloads)
        )

    def test_article(self, taskid: str, title: str) -> UserRssArticleTestDTO:
        result: Any = self._checker.test_rss_articles(
            taskid=taskid, title=title)
        if not result:
            return UserRssArticleTestDTO(name="无法识别")
        media_info, match_flag, exist_flag = result
        if not media_info:
            return UserRssArticleTestDTO(name="无法识别")
        media_dict = mediainfo_dict(media_info)
        media_dict.update({"match_flag": match_flag, "exist_flag": exist_flag})
        return UserRssArticleTestDTO(
            name=media_info.get_name(),
            match_flag=match_flag,
            exist_flag=exist_flag,
            media_dict=media_dict
        )

    def check_articles(self, taskid, flag, articles) -> Optional[bool]:
        return self._checker.check_rss_articles(
            taskid=taskid, flag=flag, articles=articles)

    def download_articles(self, taskid, articles) -> Optional[bool]:
        return self._checker.download_rss_articles(
            taskid=taskid, articles=articles)

    def run_task(self, taskid) -> None:
        self._checker.check_task_rss(taskid)

    def update_parser(self, params: dict) -> Optional[bool]:
        return self._checker.update_userrss_parser(params)

    def update_task(self, data: dict) -> UserRssTaskUpdateDTO:
        uses = data.get("uses")
        address_parser = data.get("address_parser")
        if not address_parser:
            return UserRssTaskUpdateDTO(success=False)

        address = list(dict(sorted(
            {k.replace("address_", ""): y for k, y in address_parser.items()
             if k.startswith("address_")}.items(),
            key=lambda x: int(x[0])
        )).values())
        parser = list(dict(sorted(
            {k.replace("parser_", ""): y for k, y in address_parser.items()
             if k.startswith("parser_")}.items(),
            key=lambda x: int(x[0])
        )).values())

        params = {
            "id": data.get("id"),
            "name": data.get("name"),
            "address": address,
            "parser": parser,
            "interval": data.get("interval"),
            "uses": uses,
            "include": data.get("include"),
            "exclude": data.get("exclude"),
            "filter_rule": data.get("rule"),
            "state": data.get("state"),
            "save_path": data.get("save_path"),
            "download_setting": data.get("download_setting"),
            "note": {"proxy": data.get("proxy")},
        }
        if uses == "D":
            params.update({"recognization": data.get("recognization")})
        elif uses == "R":
            params.update({
                "over_edition": data.get("over_edition"),
                "sites": data.get("sites"),
                "filter_args": {
                    "restype": data.get("restype"),
                    "pix": data.get("pix"),
                    "team": data.get("team")
                }
            })
        else:
            return UserRssTaskUpdateDTO(success=False)

        ret = self._checker.update_userrss_task(params)
        return UserRssTaskUpdateDTO(success=bool(ret))

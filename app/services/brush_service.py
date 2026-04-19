# -*- coding: utf-8 -*-
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.brushtask import BrushTask


_RSS_RULE_FIELDS = {
    "free": "brushtask_free",
    "hr": "brushtask_hr",
    "size": "brushtask_torrent_size",
    "include": "brushtask_include",
    "exclude": "brushtask_exclude",
    "dlcount": "brushtask_dlcount",
    "peercount": "brushtask_peercount",
    "pubdate": "brushtask_pubdate",
    "upspeed": "brushtask_upspeed",
    "downspeed": "brushtask_downspeed",
    "exclude_subscribe": "brushtask_exclude_subscribe",
}
_REMOVE_RULE_FIELDS = {
    "mode": "brushtask_mode",
    "time": "brushtask_seedtime",
    "hr_time": "brushtask_hr_seedtime",
    "ratio": "brushtask_seedratio",
    "uploadsize": "brushtask_seedsize",
    "dltime": "brushtask_dltime",
    "avg_upspeed": "brushtask_avg_upspeed",
    "iatime": "brushtask_iatime",
    "pending_time": "brushtask_pending_time",
    "freespace": "brushtask_freespace",
    "freestatus": "brushtask_freestatus",
}
_STOP_RULE_FIELDS = {
    "stopfree": "brushtask_stopfree",
}


@dataclass
class BrushTaskDTO:
    task: Any = None


@dataclass
class BrushTorrentListDTO:
    torrents: Optional[List[dict]] = None


class BrushService:
    """刷流任务业务服务"""

    def __init__(self, brush_task: Optional[BrushTask] = None):
        self._brush = brush_task or BrushTask()

    def build_task_item(self, data: dict) -> dict:
        """将前端参数转换为刷流任务 item 字典"""
        rss_rule = {k: data.get(v) for k, v in _RSS_RULE_FIELDS.items()}
        remove_rule = {k: data.get(v) for k, v in _REMOVE_RULE_FIELDS.items()}
        stop_rule = {k: ('Y' if data.get(v) else 'N')
                     for k, v in _STOP_RULE_FIELDS.items()}

        brushtask_totalsize = data.get("brushtask_totalsize")
        try:
            seed_size_bytes = int(float(brushtask_totalsize) * 1024 ** 3) \
                if brushtask_totalsize else 0
        except (ValueError, TypeError):
            seed_size_bytes = 0

        return {
            "name": data.get("brushtask_name"),
            "site": data.get("brushtask_site"),
            "free": data.get("brushtask_free"),
            "rssurl": data.get("brushtask_rssurl"),
            "interval": data.get("brushtask_interval"),
            "downloader": data.get("brushtask_downloader"),
            "seed_size": seed_size_bytes,
            "time_range": data.get("brushtask_time_range"),
            "label": data.get("brushtask_label"),
            "savepath": data.get("brushtask_savepath"),
            "transfer": 'Y' if data.get("brushtask_transfer") else 'N',
            "state": data.get("brushtask_state"),
            "rss_rule": rss_rule,
            "remove_rule": remove_rule,
            "stop_rule": stop_rule,
            "sendmessage": 'Y' if data.get("brushtask_sendmessage") else 'N',
        }

    def add_or_update_task(self, data: dict) -> None:
        item = self.build_task_item(data)
        self._brush.update_brushtask(data.get("brushtask_id"), item)

    def get_task(self, taskid) -> BrushTaskDTO:
        task = self._brush.get_brushtask_info(taskid)
        return BrushTaskDTO(task=task)

    def get_tasks(self):
        return self._brush.get_brushtask_info()

    def delete_task(self, taskid) -> None:
        self._brush.delete_brushtask(taskid)

    def get_torrents(self, taskid) -> BrushTorrentListDTO:
        results = self._brush.get_brushtask_torrents(
            brush_id=taskid, active=False)
        if not results:
            return BrushTorrentListDTO(torrents=None)
        return BrushTorrentListDTO(
            torrents=[item.as_dict() for item in results])

    def run_task(self, taskid) -> None:
        self._brush.check_task_rss(taskid)

    def update_task_state(self, state, task_ids: Optional[list] = None) -> None:
        if state is not None:
            if task_ids:
                for tid in task_ids:
                    self._brush.update_brushtask_state(
                        state=state, brushtask_id=tid)
            else:
                self._brush.update_brushtask_state(state=state)

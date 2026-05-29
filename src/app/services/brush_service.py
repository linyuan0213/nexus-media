import json
from datetime import datetime

from app.core.exceptions import DomainError, RepositoryError, ServiceError  # noqa: F401
from app.domain.engine.brush_rule_engine import BrushRuleEngine
from app.infrastructure.distributed_lock.lock_manager import get_lock_manager
from app.schemas.brush import (
    BrushTaskDTO,
    BrushTorrentListDTO,
)
from app.services.brush_core import BrushTaskService as BrushTask
from app.di import container

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


class BrushService:
    """刷流任务业务服务"""

    def __init__(self, brush_task: BrushTask | None = None):
        self._brush = brush_task or BrushTask()
        self._rule_repo = container.brush_rule_repo()

    def build_task_item(self, data: dict) -> dict:
        """将前端参数转换为刷流任务 item 字典"""
        rule_id = data.get("brushtask_rule_id") or None

        if rule_id:
            rss_rule = {}
            remove_rule = {}
            stop_rule = {}
        else:
            rss_rule = {k: data.get(v) for k, v in _RSS_RULE_FIELDS.items()}
            remove_rule = {k: data.get(v) for k, v in _REMOVE_RULE_FIELDS.items()}
            stop_rule = {k: ("Y" if data.get(v) else "N") for k, v in _STOP_RULE_FIELDS.items()}

        brushtask_totalsize = data.get("brushtask_totalsize")
        try:
            seed_size_bytes = int(float(brushtask_totalsize) * 1024**3) if brushtask_totalsize else 0
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
            "transfer": "Y" if data.get("brushtask_transfer") else "N",
            "state": data.get("brushtask_state"),
            "rss_rule": rss_rule,
            "remove_rule": remove_rule,
            "stop_rule": stop_rule,
            "rule_id": rule_id,
            "sendmessage": "Y" if data.get("brushtask_sendmessage") else "N",
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
        results = self._brush.get_brushtask_torrents(brush_id=taskid, active=False)
        if not results:
            return BrushTorrentListDTO(torrents=None)
        return BrushTorrentListDTO(torrents=[item.as_dict() for item in results])

    def run_task(self, taskid) -> None:
        lock_key = f"brush:run_task:{taskid}"
        lock = get_lock_manager().create_lock(lock_key, ttl_seconds=300)
        acquired = lock.acquire()
        if not acquired:
            return
        try:
            self._brush.check_task_rss(taskid)
        finally:
            lock.release()

    def update_task_state(self, state, task_ids: list | None = None) -> None:
        if state is not None:
            if task_ids:
                for tid in task_ids:
                    self._brush.update_brushtask_state(state=state, brushtask_id=tid)
            else:
                self._brush.update_brushtask_state(state=state)

    # ---------- 规则模板管理 ----------

    def get_rules(self) -> list[dict]:
        return [r.to_dict() for r in self._rule_repo.get_all()]

    def get_rule(self, rule_id: int) -> dict | None:
        entity = self._rule_repo.get_by_id(rule_id)
        return entity.to_dict() if entity else None

    def add_rule(self, data: dict) -> int:
        return self._rule_repo.insert(
            name=data.get("name", ""),
            rss_rule=json.dumps(data.get("rss_rule", {}), ensure_ascii=False),
            remove_rule=json.dumps(data.get("remove_rule", {}), ensure_ascii=False),
            stop_rule=json.dumps(data.get("stop_rule", {}), ensure_ascii=False),
        )

    def update_rule(self, rule_id: int, data: dict) -> None:
        self._rule_repo.update(
            rule_id=rule_id,
            name=data.get("name"),
            rss_rule=json.dumps(data.get("rss_rule", {}), ensure_ascii=False) if "rss_rule" in data else None,
            remove_rule=json.dumps(data.get("remove_rule", {}), ensure_ascii=False) if "remove_rule" in data else None,
            stop_rule=json.dumps(data.get("stop_rule", {}), ensure_ascii=False) if "stop_rule" in data else None,
        )

    def delete_rule(self, rule_id: int) -> None:
        self._rule_repo.delete(rule_id)

    # ---------- 规则引擎委托 ----------

    @staticmethod
    def check_rss_rule(
        rss_rule: dict, title: str, torrent_size: float, pubdate: datetime | None, torrent_attr: dict
    ) -> bool:
        """委托给领域规则引擎：检查种子是否符合刷流RSS选种规则"""
        return BrushRuleEngine.check_rss_rule(
            rss_rule=rss_rule, title=title, torrent_size=torrent_size, pubdate=pubdate, torrent_attr=torrent_attr
        )

    @staticmethod
    def check_remove_rule(remove_rule: dict | None, params: dict):
        """委托给领域规则引擎：检查是否符合删种规则"""
        return BrushRuleEngine.check_remove_rule(remove_rule=remove_rule, params=params)

    @staticmethod
    def check_stop_rule(stop_rule: dict | None, torrent_attr: dict):
        """委托给领域规则引擎：检查是否符合停种规则"""
        return BrushRuleEngine.check_stop_rule(stop_rule=stop_rule, params=torrent_attr)

    @staticmethod
    def format_rule_html(rules: dict | None) -> str:
        """委托给领域规则引擎：将规则字典渲染为 HTML badge 字符串"""
        return BrushRuleEngine.format_rule_html(rules)

    @staticmethod
    def check_range_rule(value, rule_value: str, multiplier: float = 1.0) -> bool:
        """委托给领域规则引擎：通用范围规则检查"""
        return BrushRuleEngine.check_range_rule(value=value, rule_value=rule_value, multiplier=multiplier)

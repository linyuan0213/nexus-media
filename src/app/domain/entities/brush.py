"""
刷流领域实体
"""

from dataclasses import dataclass, fields
from enum import Enum
from typing import Any, Optional

from app.utils.json_utils import JsonUtils


class BrushTaskState(Enum):
    """刷流任务状态值对象"""

    RUNNING = "Y"
    STOPPED = "S"
    DISABLED = "N"

    @classmethod
    def from_value(cls, value: str) -> "BrushTaskState":
        for member in cls:
            if member.value == value:
                return member
        return cls.DISABLED

    @property
    def display_name(self) -> str:
        return {
            "Y": "运行中",
            "S": "已停止",
            "N": "已禁用",
        }.get(self.value, self.value)


@dataclass
class BrushRuleEntity:
    """刷流规则模板实体"""

    id: int
    name: str
    type: str
    rss_rule: str
    remove_rule: str
    stop_rule: str
    lst_mod_date: str

    @classmethod
    def from_orm(cls, orm_model) -> Optional["BrushRuleEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            name=orm_model.NAME or "",
            type=orm_model.TYPE or "all",
            rss_rule=orm_model.RSS_RULE or "",
            remove_rule=orm_model.REMOVE_RULE or "",
            stop_rule=orm_model.STOP_RULE or "",
            lst_mod_date=orm_model.LST_MOD_DATE or "",
        )

    def to_dict(self) -> dict[str, Any]:
        def _parse(val: str) -> dict[str, Any]:
            if not val:
                return {}
            try:
                return JsonUtils.loads(val) if isinstance(val, str) else val
            except Exception:
                return {}

        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "rss_rule": _parse(self.rss_rule),
            "remove_rule": _parse(self.remove_rule),
            "stop_rule": _parse(self.stop_rule),
            "lst_mod_date": self.lst_mod_date,
        }


@dataclass
class BrushTaskEntity:
    """刷流任务实体"""

    id: int
    name: str
    site: str
    rss_url: str
    freeleech: str
    rss_rule: str
    remove_rule: str
    stop_rule: str
    rss_rule_id: int | None
    remove_rule_id: int | None
    stop_rule_id: int | None
    seed_size: int
    time_range: str
    interval: str
    label: str
    save_path: str
    downloader: str
    transfer: str
    download_count: int
    remove_count: int
    download_size: int
    upload_size: int
    send_message: str
    state: str
    lst_mod_date: str

    @property
    def state_enum(self) -> BrushTaskState:
        return BrushTaskState.from_value(self.state)

    @property
    def is_running(self) -> bool:
        return self.state == BrushTaskState.RUNNING.value

    @property
    def is_stopped(self) -> bool:
        return self.state == BrushTaskState.STOPPED.value

    @property
    def is_disabled(self) -> bool:
        return self.state not in (BrushTaskState.RUNNING.value, BrushTaskState.STOPPED.value)

    @property
    def is_scheduled(self) -> bool:
        """是否需要调度（运行中或已停止但仍需清理）"""
        return self.state in (BrushTaskState.RUNNING.value, BrushTaskState.STOPPED.value)

    @property
    def can_download_new(self) -> bool:
        """是否可以下载新种子"""
        return self.is_running and bool(self.rss_url)

    @property
    def has_valid_interval(self) -> bool:
        """运行周期格式是否有效"""
        cron = str(self.interval).strip()
        return cron.isdigit() or cron.count(" ") == 4

    def mark_running(self) -> None:
        self.state = BrushTaskState.RUNNING.value

    def mark_stopped(self) -> None:
        self.state = BrushTaskState.STOPPED.value

    def mark_disabled(self) -> None:
        self.state = BrushTaskState.DISABLED.value

    def __getattr__(self, name: str):
        """兼容旧代码的大写属性访问（如 task.ID -> task.id）"""
        lower_name = name.lower()
        if lower_name in {f.name for f in fields(self)}:
            return getattr(self, lower_name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    @classmethod
    def from_orm(cls, orm_model) -> Optional["BrushTaskEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            name=orm_model.NAME or "",
            site=orm_model.SITE or "",
            rss_url=orm_model.RSSURL or "",
            freeleech=orm_model.FREELEECH or "",
            rss_rule=orm_model.RSS_RULE or "",
            remove_rule=orm_model.REMOVE_RULE or "",
            stop_rule=orm_model.STOP_RULE or "",
            rss_rule_id=orm_model.RSS_RULE_ID or None,
            remove_rule_id=orm_model.REMOVE_RULE_ID or None,
            stop_rule_id=orm_model.STOP_RULE_ID or None,
            seed_size=orm_model.SEED_SIZE or 0,
            time_range=orm_model.TIME_RANGE or "",
            interval=orm_model.INTEVAL or "",
            label=orm_model.LABEL or "",
            save_path=orm_model.SAVEPATH or "",
            downloader=orm_model.DOWNLOADER or "",
            transfer=orm_model.TRANSFER or "",
            download_count=orm_model.DOWNLOAD_COUNT or 0,
            remove_count=orm_model.REMOVE_COUNT or 0,
            download_size=orm_model.DOWNLOAD_SIZE or 0,
            upload_size=orm_model.UPLOAD_SIZE or 0,
            send_message=orm_model.SENDMESSAGE or "",
            state=orm_model.STATE or "",
            lst_mod_date=orm_model.LST_MOD_DATE or "",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "site": self.site,
            "rss_url": self.rss_url,
            "freeleech": self.freeleech,
            "rss_rule": self.rss_rule,
            "remove_rule": self.remove_rule,
            "stop_rule": self.stop_rule,
            "rss_rule_id": self.rss_rule_id,
            "remove_rule_id": self.remove_rule_id,
            "stop_rule_id": self.stop_rule_id,
            "seed_size": self.seed_size,
            "time_range": self.time_range,
            "interval": self.interval,
            "label": self.label,
            "save_path": self.save_path,
            "downloader": self.downloader,
            "transfer": self.transfer,
            "download_count": self.download_count,
            "remove_count": self.remove_count,
            "download_size": self.download_size,
            "upload_size": self.upload_size,
            "send_message": self.send_message,
            "state": self.state,
            "lst_mod_date": self.lst_mod_date,
        }


@dataclass
class BrushTorrentEntity:
    """刷流种子实体"""

    id: int
    task_id: str
    torrent_name: str
    torrent_size: str
    enclosure: str
    downloader: str
    download_id: str
    lst_mod_date: str

    @classmethod
    def from_orm(cls, orm_model) -> Optional["BrushTorrentEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            task_id=orm_model.TASK_ID or "",
            torrent_name=orm_model.TORRENT_NAME or "",
            torrent_size=orm_model.TORRENT_SIZE or "",
            enclosure=orm_model.ENCLOSURE or "",
            downloader=orm_model.DOWNLOADER or "",
            download_id=orm_model.DOWNLOAD_ID or "",
            lst_mod_date=orm_model.LST_MOD_DATE or "",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "torrent_name": self.torrent_name,
            "torrent_size": self.torrent_size,
            "enclosure": self.enclosure,
            "downloader": self.downloader,
            "download_id": self.download_id,
            "lst_mod_date": self.lst_mod_date,
        }

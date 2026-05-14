"""
刷流领域实体
"""

from dataclasses import dataclass, fields
from typing import Any, Optional


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

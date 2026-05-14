"""
Brush Repository
Handles brush task and torrent related database operations.
"""

import json
import time

from sqlalchemy import Integer, cast, func

from app.db import DbPersist
from app.db.models import CONFIGSITE, SITEBRUSHTASK, SITEBRUSHTORRENTS
from app.db.repositories.base_repository import BaseRepository
from app.sites.engine import SiteEngine
from app.utils import StringUtils


class BrushRepository(BaseRepository):
    """
    刷流任务仓储
    处理刷流任务和种子信息的数据库操作
    """

    @DbPersist(BaseRepository._db)
    def update_brushtask(self, brush_id: int | None, item: dict) -> None:
        """
        新增或更新刷流任务
        """
        if not brush_id:
            self._db.insert(
                SITEBRUSHTASK(
                    NAME=item.get("name"),
                    SITE=item.get("site"),
                    FREELEECH=item.get("free"),
                    RSS_RULE=json.dumps(item.get("rss_rule"), ensure_ascii=False),
                    REMOVE_RULE=json.dumps(item.get("remove_rule"), ensure_ascii=False),
                    STOP_RULE=json.dumps(item.get("stop_rule"), ensure_ascii=False),
                    SEED_SIZE=item.get("seed_size"),
                    TIME_RANGE=item.get("time_range"),
                    RSSURL=item.get("rssurl"),
                    INTEVAL=item.get("interval"),
                    DOWNLOADER=item.get("downloader"),
                    LABEL=item.get("label"),
                    SAVEPATH=item.get("savepath"),
                    TRANSFER=item.get("transfer"),
                    DOWNLOAD_COUNT=0,
                    REMOVE_COUNT=0,
                    DOWNLOAD_SIZE=0,
                    UPLOAD_SIZE=0,
                    STATE=item.get("state"),
                    LST_MOD_DATE=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time())),
                    SENDMESSAGE=item.get("sendmessage"),
                )
            )
        else:
            self._db.query(SITEBRUSHTASK).filter(int(brush_id) == SITEBRUSHTASK.ID).update(
                {
                    "NAME": item.get("name"),
                    "SITE": item.get("site"),
                    "FREELEECH": item.get("free"),
                    "RSS_RULE": json.dumps(item.get("rss_rule"), ensure_ascii=False),
                    "REMOVE_RULE": json.dumps(item.get("remove_rule"), ensure_ascii=False),
                    "STOP_RULE": json.dumps(item.get("stop_rule"), ensure_ascii=False),
                    "SEED_SIZE": item.get("seed_size"),
                    "TIME_RANGE": item.get("time_range"),
                    "RSSURL": item.get("rssurl"),
                    "INTEVAL": item.get("interval"),
                    "DOWNLOADER": item.get("downloader"),
                    "LABEL": item.get("label"),
                    "SAVEPATH": item.get("savepath"),
                    "TRANSFER": item.get("transfer"),
                    "STATE": item.get("state"),
                    "LST_MOD_DATE": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time())),
                    "SENDMESSAGE": item.get("sendmessage"),
                }
            )

    @DbPersist(BaseRepository._db)
    def delete_brushtask(self, brush_id: int) -> None:
        """
        删除刷流任务
        """
        self._db.query(SITEBRUSHTASK).filter(int(brush_id) == SITEBRUSHTASK.ID).delete()
        self._db.query(SITEBRUSHTORRENTS).filter(brush_id == SITEBRUSHTORRENTS.TASK_ID).delete()

    def get_brushtasks(self, brush_id: int | None = None) -> SITEBRUSHTASK | None | list[SITEBRUSHTASK]:
        """
        查询刷流任务
        """
        if brush_id:
            return self._db.query(SITEBRUSHTASK).filter(int(brush_id) == SITEBRUSHTASK.ID).first()
        else:
            return (
                self._db.query(SITEBRUSHTASK)
                .join(CONFIGSITE, SITEBRUSHTASK.SITE == CONFIGSITE.ID)
                .order_by(cast(CONFIGSITE.PRI, Integer).asc())
                .all()
            )

    def get_brushtask_totalsize(self, brush_id: int | None) -> int:
        """
        查询刷流任务总体积
        """
        if not brush_id:
            return 0
        ret = (
            self._db.query(func.sum(cast(SITEBRUSHTORRENTS.TORRENT_SIZE, Integer)))
            .filter(
                brush_id == SITEBRUSHTORRENTS.TASK_ID,
                SITEBRUSHTORRENTS.DOWNLOAD_ID != "0",
                SITEBRUSHTORRENTS.TORRENT_SIZE != "",
                SITEBRUSHTORRENTS.TORRENT_SIZE.isnot(None),
            )
            .first()
        )
        return ret[0] or 0 if ret else 0

    @DbPersist(BaseRepository._db)
    def update_brushtask_state(self, state: str, tid: int | None = None) -> None:
        """
        改变刷流任务的状态
        """
        if tid:
            self._db.query(SITEBRUSHTASK).filter(int(tid) == SITEBRUSHTASK.ID).update(
                {"STATE": "Y" if state == "Y" else "N"}
            )
        else:
            self._db.query(SITEBRUSHTASK).update({"STATE": "Y" if state == "Y" else "N"})

    @DbPersist(BaseRepository._db)
    def add_brushtask_download_count(self, brush_id: int | None) -> None:
        """
        增加刷流下载数
        """
        if not brush_id:
            return
        self._db.query(SITEBRUSHTASK).filter(int(brush_id) == SITEBRUSHTASK.ID).update(
            {
                "DOWNLOAD_COUNT": SITEBRUSHTASK.DOWNLOAD_COUNT + 1,
                "LST_MOD_DATE": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time())),
            }
        )

    def get_brushtask_remove_size(self, brush_id: int | None) -> int | list[tuple]:
        """
        获取已删除种子的上传量
        """
        if not brush_id:
            return 0
        return (
            self._db.query(SITEBRUSHTORRENTS.TORRENT_SIZE)
            .filter(brush_id == SITEBRUSHTORRENTS.TASK_ID, SITEBRUSHTORRENTS.DOWNLOAD_ID == "0")
            .all()
        )

    @DbPersist(BaseRepository._db)
    def add_brushtask_upload_count(self, brush_id: int | None, upload_size: int, download_size: int, remove_count: int) -> None:
        """
        更新上传下载量和删除种子数
        """
        if not brush_id:
            return
        delete_upsize = 0
        delete_dlsize = 0
        remove_sizes = self.get_brushtask_remove_size(brush_id)
        for remove_size in remove_sizes:
            if not remove_size[0]:
                continue
            if str(remove_size[0]).find(",") != -1:
                sizes = str(remove_size[0]).split(",")
                delete_upsize += int(sizes[0] or 0)
                if len(sizes) > 1:
                    delete_dlsize += int(sizes[1] or 0)
            else:
                delete_upsize += int(remove_size[0])

        self._db.query(SITEBRUSHTASK).filter(int(brush_id) == SITEBRUSHTASK.ID).update(
            {
                "REMOVE_COUNT": SITEBRUSHTASK.REMOVE_COUNT + remove_count,
                "UPLOAD_SIZE": int(upload_size) + delete_upsize,
                "DOWNLOAD_SIZE": int(download_size) + delete_dlsize,
            }
        )

    @DbPersist(BaseRepository._db)
    def insert_brushtask_torrent(self, brush_id: int | None, title: str, enclosure: str, downloader: str, download_id: str, size: str) -> None:
        """
        增加刷流下载的种子信息
        """
        if not brush_id:
            return
        # 截断超长 ENCLOSURE：去掉磁力链接中多余的 tracker，只保留核心 btih
        if enclosure and enclosure.startswith("magnet:"):
            enclosure = enclosure.split("&")[0]
        elif enclosure and len(enclosure) > 4000:
            enclosure = enclosure[:4000]
        if self.is_brushtask_torrent_exists(brush_id, title, enclosure):
            return

        self._db.insert(
            SITEBRUSHTORRENTS(
                TASK_ID=brush_id,
                TORRENT_NAME=title,
                TORRENT_SIZE=size,
                ENCLOSURE=enclosure,
                DOWNLOADER=downloader,
                DOWNLOAD_ID=download_id,
                LST_MOD_DATE=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time())),
            )
        )

    def get_brushtask_torrents(self, brush_id: int | None, active: bool = True) -> list[SITEBRUSHTORRENTS]:
        """
        查询刷流任务所有种子
        """
        if not brush_id:
            return []
        if active:
            return (
                self._db.query(SITEBRUSHTORRENTS)
                .filter(int(brush_id) == SITEBRUSHTORRENTS.TASK_ID, SITEBRUSHTORRENTS.DOWNLOAD_ID != "0")
                .all()
            )
        else:
            return (
                self._db.query(SITEBRUSHTORRENTS)
                .filter(int(brush_id) == SITEBRUSHTORRENTS.TASK_ID)
                .order_by(SITEBRUSHTORRENTS.LST_MOD_DATE.desc())
                .all()
            )

    def get_brushtask_torrent_by_enclosure(self, enclosure: str) -> SITEBRUSHTORRENTS | None | list[SITEBRUSHTORRENTS]:
        """
        根据URL查询刷流任务种子
        """

        if not enclosure:
            return None

        engine = SiteEngine.get_instance()
        if engine.is_tid_based_dedup(enclosure):
            tid = StringUtils.get_tid_by_url(enclosure)
            domain = engine.normalize_domain(enclosure)
            all_torrents = (
                self._db.query(SITEBRUSHTORRENTS).filter(SITEBRUSHTORRENTS.ENCLOSURE.like(f"%{domain}%")).all()
            )
            return list(filter(lambda t: StringUtils.get_tid_by_url(t.ENCLOSURE) == tid, all_torrents))

        return self._db.query(SITEBRUSHTORRENTS).filter(enclosure == SITEBRUSHTORRENTS.ENCLOSURE).first()

    def is_brushtask_torrent_exists(self, brush_id: int | None, title: str, enclosure: str) -> bool:
        """
        查询刷流任务种子是否已存在
        """
        if not brush_id:
            return False
        count = (
            self._db.query(SITEBRUSHTORRENTS)
            .filter(
                brush_id == SITEBRUSHTORRENTS.TASK_ID,
                title == SITEBRUSHTORRENTS.TORRENT_NAME,
                enclosure == SITEBRUSHTORRENTS.ENCLOSURE,
            )
            .count()
        )
        return count > 0

    @DbPersist(BaseRepository._db)
    def update_brushtask_torrent_state(self, ids: list) -> None:
        """
        更新刷流种子的状态
        """
        if not ids:
            return
        for _id in ids:
            self._db.query(SITEBRUSHTORRENTS).filter(
                _id[1] == SITEBRUSHTORRENTS.TASK_ID, _id[2] == SITEBRUSHTORRENTS.DOWNLOAD_ID
            ).update({"TORRENT_SIZE": _id[0], "DOWNLOAD_ID": "0"})

    @DbPersist(BaseRepository._db)
    def delete_brushtask_torrent(self, brush_id: int | None, download_id: str | None) -> None:
        """
        删除刷流种子记录
        """
        if not download_id or not brush_id:
            return
        self._db.query(SITEBRUSHTORRENTS).filter(
            brush_id == SITEBRUSHTORRENTS.TASK_ID, download_id == SITEBRUSHTORRENTS.DOWNLOAD_ID
        ).delete()

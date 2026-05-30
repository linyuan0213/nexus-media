"""
Brush Repository
Handles brush task and torrent related database operations.
"""

import json
import time
from typing import Any

from sqlalchemy import Integer, cast, func

from app.db import auto_commit
from app.db.models import CONFIGSITE, SITEBRUSHRULE, SITEBRUSHTASK, SITEBRUSHTORRENTS
from app.db.repositories.base_repository import BaseRepository


class BrushRepository(BaseRepository):
    """
    刷流任务仓储
    处理刷流任务和种子信息的数据库操作
    """

    @auto_commit(BaseRepository._db)
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
                    RULE_ID=item.get("rule_id"),
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
                    "RULE_ID": item.get("rule_id"),
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

    @auto_commit(BaseRepository._db)
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

    @auto_commit(BaseRepository._db)
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

    @auto_commit(BaseRepository._db)
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

    def get_brushtask_remove_size(self, brush_id: int | None) -> list[tuple]:
        """
        获取已删除种子的上传量
        """
        if not brush_id:
            return []
        return (
            self._db.query(SITEBRUSHTORRENTS.TORRENT_SIZE)
            .filter(brush_id == SITEBRUSHTORRENTS.TASK_ID, SITEBRUSHTORRENTS.DOWNLOAD_ID == "0")
            .all()
        )

    @auto_commit(BaseRepository._db)
    def add_brushtask_upload_count(
        self, brush_id: int | None, upload_size: int, download_size: int, remove_count: int
    ) -> None:
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

    @auto_commit(BaseRepository._db)
    def insert_brushtask_torrent(
        self, brush_id: int | None, title: str, enclosure: str, downloader: str, download_id: str, size: str
    ) -> None:
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

    def get_brushtask_torrent_by_enclosure(self, enclosure: str) -> SITEBRUSHTORRENTS | None:
        """
        根据URL精确查询刷流任务种子
        """
        if not enclosure:
            return None
        return self._db.query(SITEBRUSHTORRENTS).filter(enclosure == SITEBRUSHTORRENTS.ENCLOSURE).first()

    def get_brushtask_torrents_by_domain(self, domain: str) -> list[SITEBRUSHTORRENTS]:
        """
        根据域名模糊查询刷流任务种子（供 tid-based dedup 使用）
        """
        if not domain:
            return []
        return self._db.query(SITEBRUSHTORRENTS).filter(SITEBRUSHTORRENTS.ENCLOSURE.like(f"%{domain}%")).all()

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

    @auto_commit(BaseRepository._db)
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

    @auto_commit(BaseRepository._db)
    def delete_brushtask_torrent(self, brush_id: int | None, download_id: str | None) -> None:
        """
        删除刷流种子记录
        """
        if not download_id or not brush_id:
            return
        self._db.query(SITEBRUSHTORRENTS).filter(
            brush_id == SITEBRUSHTORRENTS.TASK_ID, download_id == SITEBRUSHTORRENTS.DOWNLOAD_ID
        ).delete()

    # ---------- 刷流规则模板 ----------

    @auto_commit(BaseRepository._db)
    def insert_brushrule(self, name: str, rss_rule: str, remove_rule: str, stop_rule: str) -> int:
        """新增刷流规则模板，返回自增 ID。"""
        entity = SITEBRUSHRULE(
            NAME=name,
            RSS_RULE=rss_rule,
            REMOVE_RULE=remove_rule,
            STOP_RULE=stop_rule,
            LST_MOD_DATE=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time())),
        )
        self._db.insert(entity)
        return entity.ID

    @auto_commit(BaseRepository._db)
    def update_brushrule(
        self, rule_id: int, name: str | None, rss_rule: str | None, remove_rule: str | None, stop_rule: str | None
    ) -> None:
        """更新刷流规则模板。"""
        updates: dict[str, Any] = {}
        if name is not None:
            updates["NAME"] = name
        if rss_rule is not None:
            updates["RSS_RULE"] = rss_rule
        if remove_rule is not None:
            updates["REMOVE_RULE"] = remove_rule
        if stop_rule is not None:
            updates["STOP_RULE"] = stop_rule
        if updates:
            updates["LST_MOD_DATE"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time()))
            self._db.query(SITEBRUSHRULE).filter(int(rule_id) == SITEBRUSHRULE.ID).update(updates)

    def get_brushrules(self, rule_id: int | None = None) -> SITEBRUSHRULE | None | list[SITEBRUSHRULE]:
        """查询刷流规则模板。"""
        if rule_id:
            return self._db.query(SITEBRUSHRULE).filter(int(rule_id) == SITEBRUSHRULE.ID).first()
        return self._db.query(SITEBRUSHRULE).order_by(SITEBRUSHRULE.ID.desc()).all()

    @auto_commit(BaseRepository._db)
    def delete_brushrule(self, rule_id: int) -> None:
        """删除刷流规则模板，并将关联任务的 RULE_ID 置空。"""
        self._db.query(SITEBRUSHTASK).filter(int(rule_id) == SITEBRUSHTASK.RULE_ID).update({"RULE_ID": None})
        self._db.query(SITEBRUSHRULE).filter(int(rule_id) == SITEBRUSHRULE.ID).delete()

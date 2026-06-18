"""
Brush Repository
Handles brush task and torrent related database operations.
"""

import time
from typing import Any

from sqlalchemy import Integer, and_, case, cast, func, or_

from app.db.models import CONFIGSITE, SITEBRUSHRULE, SITEBRUSHTASK, SITEBRUSHTORRENTS
from app.db.repositories.base_repository import BaseRepository
from app.utils.json_utils import JsonUtils


class BrushRepository(BaseRepository):
    """
    刷流任务仓储
    处理刷流任务和种子信息的数据库操作
    """

    def update_brushtask(self, brush_id: int | None, item: dict) -> None:
        """
        新增或更新刷流任务
        """
        with self.session() as db:
            if not brush_id:
                db.add(
                    SITEBRUSHTASK(
                        NAME=item.get("name"),
                        SITE=item.get("site"),
                        FREELEECH=item.get("free"),
                        RSS_RULE=JsonUtils.dumps(item.get("rss_rule"), ensure_ascii=False),
                        REMOVE_RULE=JsonUtils.dumps(item.get("remove_rule"), ensure_ascii=False),
                        STOP_RULE=JsonUtils.dumps(item.get("stop_rule"), ensure_ascii=False),
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
                db.query(SITEBRUSHTASK).filter(int(brush_id) == SITEBRUSHTASK.ID).update(
                    {
                        "NAME": item.get("name"),
                        "SITE": item.get("site"),
                        "FREELEECH": item.get("free"),
                        "RSS_RULE": JsonUtils.dumps(item.get("rss_rule"), ensure_ascii=False),
                        "REMOVE_RULE": JsonUtils.dumps(item.get("remove_rule"), ensure_ascii=False),
                        "STOP_RULE": JsonUtils.dumps(item.get("stop_rule"), ensure_ascii=False),
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

    def delete_brushtask(self, brush_id: int) -> None:
        """
        删除刷流任务
        """
        with self.session() as db:
            db.query(SITEBRUSHTASK).filter(int(brush_id) == SITEBRUSHTASK.ID).delete()
            db.query(SITEBRUSHTORRENTS).filter(brush_id == SITEBRUSHTORRENTS.TASK_ID).delete()

    def get_brushtasks(self, brush_id: int | None = None) -> SITEBRUSHTASK | None | list[SITEBRUSHTASK]:
        """
        查询刷流任务
        """
        with self.session() as db:
            if brush_id:
                return db.query(SITEBRUSHTASK).filter(int(brush_id) == SITEBRUSHTASK.ID).first()
            else:
                return (
                    db.query(SITEBRUSHTASK)
                    .join(CONFIGSITE, cast(SITEBRUSHTASK.SITE, Integer) == CONFIGSITE.ID)
                    .order_by(cast(CONFIGSITE.PRI, Integer).asc())
                    .all()
                )

    def get_brushtask_totalsize(self, brush_id: int | None) -> int:
        """
        查询刷流任务总体积
        """
        if not brush_id:
            return 0
        with self.session() as db:
            ret = (
                db.query(func.sum(cast(SITEBRUSHTORRENTS.TORRENT_SIZE, Integer)))
                .filter(
                    brush_id == SITEBRUSHTORRENTS.TASK_ID,
                    SITEBRUSHTORRENTS.DOWNLOAD_ID != "0",
                    SITEBRUSHTORRENTS.TORRENT_SIZE != "",
                    SITEBRUSHTORRENTS.TORRENT_SIZE.isnot(None),
                )
                .first()
            )
            return ret[0] or 0 if ret else 0

    def update_brushtask_state(self, state: str, tid: int | None = None) -> None:
        """
        改变刷流任务的状态
        """
        with self.session() as db:
            if tid:
                db.query(SITEBRUSHTASK).filter(int(tid) == SITEBRUSHTASK.ID).update(
                    {"STATE": "Y" if state == "Y" else "N"}
                )
            else:
                db.query(SITEBRUSHTASK).update({"STATE": "Y" if state == "Y" else "N"})

    def add_brushtask_download_count(self, brush_id: int | None) -> None:
        """
        增加刷流下载数
        """
        if not brush_id:
            return
        with self.session() as db:
            db.query(SITEBRUSHTASK).filter(int(brush_id) == SITEBRUSHTASK.ID).update(
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
        with self.session() as db:
            return (
                db.query(SITEBRUSHTORRENTS.TORRENT_SIZE)
                .filter(brush_id == SITEBRUSHTORRENTS.TASK_ID, SITEBRUSHTORRENTS.DOWNLOAD_ID == "0")
                .all()
            )

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

        with self.session() as db:
            db.query(SITEBRUSHTASK).filter(int(brush_id) == SITEBRUSHTASK.ID).update(
                {
                    "REMOVE_COUNT": SITEBRUSHTASK.REMOVE_COUNT + remove_count,
                    "UPLOAD_SIZE": int(upload_size) + delete_upsize,
                    "DOWNLOAD_SIZE": int(download_size) + delete_dlsize,
                }
            )

    def insert_brushtask_torrent(
        self, brush_id: int | None, title: str, enclosure: str, downloader: str, download_id: str, size: str
    ) -> None:
        """
        增加刷流下载的种子信息
        """
        if not brush_id:
            return
        if enclosure and enclosure.startswith("magnet:"):
            enclosure = enclosure.split("&")[0]
        elif enclosure and len(enclosure) > 4000:
            enclosure = enclosure[:4000]
        if self.is_brushtask_torrent_exists(brush_id, title, enclosure):
            return

        with self.session() as db:
            db.add(
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
        with self.session() as db:
            if active:
                return (
                    db.query(SITEBRUSHTORRENTS)
                    .filter(int(brush_id) == SITEBRUSHTORRENTS.TASK_ID, SITEBRUSHTORRENTS.DOWNLOAD_ID != "0")
                    .all()
                )
            else:
                return (
                    db.query(SITEBRUSHTORRENTS)
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
        with self.session() as db:
            return db.query(SITEBRUSHTORRENTS).filter(enclosure == SITEBRUSHTORRENTS.ENCLOSURE).first()

    def get_brushtask_torrents_by_domain(self, domain: str) -> list[SITEBRUSHTORRENTS]:
        """
        根据域名模糊查询刷流任务种子（供 tid-based dedup 使用）
        """
        if not domain:
            return []
        with self.session() as db:
            return db.query(SITEBRUSHTORRENTS).filter(SITEBRUSHTORRENTS.ENCLOSURE.like(f"%{domain}%")).all()

    def is_brushtask_torrent_exists(self, brush_id: int | None, title: str, enclosure: str) -> bool:
        """
        查询刷流任务种子是否已存在
        """
        if not brush_id:
            return False
        with self.session() as db:
            count = (
                db.query(SITEBRUSHTORRENTS)
                .filter(
                    brush_id == SITEBRUSHTORRENTS.TASK_ID,
                    title == SITEBRUSHTORRENTS.TORRENT_NAME,
                    enclosure == SITEBRUSHTORRENTS.ENCLOSURE,
                )
                .count()
            )
            return count > 0

    def update_brushtask_torrent_state(self, ids: list) -> None:
        """
        更新刷流种子的状态
        """
        if not ids:
            return
        with self.session() as db:
            conditions = [
                and_(SITEBRUSHTORRENTS.TASK_ID == task_id, SITEBRUSHTORRENTS.DOWNLOAD_ID == download_id)
                for _, task_id, download_id in ids
            ]
            case_stmt = case(
                *[(cond, torrent_size) for (_, torrent_size), cond in zip(ids, conditions)],
                else_=SITEBRUSHTORRENTS.TORRENT_SIZE,
            )
            db.query(SITEBRUSHTORRENTS).filter(or_(*conditions)).update(
                {"TORRENT_SIZE": case_stmt, "DOWNLOAD_ID": "0"}, synchronize_session=False
            )

    def delete_brushtask_torrent(self, brush_id: int | None, download_id: str | None) -> None:
        """
        删除刷流种子记录
        """
        if not download_id or not brush_id:
            return
        with self.session() as db:
            db.query(SITEBRUSHTORRENTS).filter(
                brush_id == SITEBRUSHTORRENTS.TASK_ID, download_id == SITEBRUSHTORRENTS.DOWNLOAD_ID
            ).delete()

    # ---------- 刷流规则模板 ----------

    def insert_brushrule(self, name: str, rss_rule: str, remove_rule: str, stop_rule: str) -> int:
        """新增刷流规则模板，返回自增 ID。"""
        with self.session() as db:
            entity = SITEBRUSHRULE(
                NAME=name,
                RSS_RULE=rss_rule,
                REMOVE_RULE=remove_rule,
                STOP_RULE=stop_rule,
                LST_MOD_DATE=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time())),
            )
            db.add(entity)
            db.flush()
            return entity.ID

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
            with self.session() as db:
                db.query(SITEBRUSHRULE).filter(int(rule_id) == SITEBRUSHRULE.ID).update(updates)

    def get_brushrules(self, rule_id: int | None = None) -> SITEBRUSHRULE | None | list[SITEBRUSHRULE]:
        """查询刷流规则模板。"""
        with self.session() as db:
            if rule_id:
                return db.query(SITEBRUSHRULE).filter(int(rule_id) == SITEBRUSHRULE.ID).first()
            return db.query(SITEBRUSHRULE).order_by(SITEBRUSHRULE.ID.desc()).all()

    def delete_brushrule(self, rule_id: int) -> None:
        """删除刷流规则模板，并将关联任务的 RULE_ID 置空。"""
        with self.session() as db:
            db.query(SITEBRUSHTASK).filter(int(rule_id) == SITEBRUSHTASK.RULE_ID).update({"RULE_ID": None})
            db.query(SITEBRUSHRULE).filter(int(rule_id) == SITEBRUSHRULE.ID).delete()

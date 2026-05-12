"""
Brush Repository
Handles brush task and torrent related database operations.
"""
import json
import time

from sqlalchemy import cast, Integer, func

from app.db import DbPersist
from app.db.models import SITEBRUSHTASK, SITEBRUSHTORRENTS, CONFIGSITE
from app.db.repositories.base_repository import BaseRepository


class BrushRepository(BaseRepository):
    """
    刷流任务仓储
    处理刷流任务和种子信息的数据库操作
    """

    @DbPersist(BaseRepository._db)
    def update_brushtask(self, brush_id, item):
        """
        新增或更新刷流任务
        """
        if not brush_id:
            self._db.insert(SITEBRUSHTASK(
                NAME=item.get('name'),
                SITE=item.get('site'),
                FREELEECH=item.get('free'),
                RSS_RULE=json.dumps(item.get('rss_rule'), ensure_ascii=False),
                REMOVE_RULE=json.dumps(item.get('remove_rule'), ensure_ascii=False),
                STOP_RULE=json.dumps(item.get('stop_rule'), ensure_ascii=False),
                SEED_SIZE=item.get('seed_size'),
                TIME_RANGE=item.get('time_range'),
                RSSURL=item.get('rssurl'),
                INTEVAL=item.get('interval'),
                DOWNLOADER=item.get('downloader'),
                LABEL=item.get('label'),
                SAVEPATH=item.get('savepath'),
                TRANSFER=item.get('transfer'),
                DOWNLOAD_COUNT=0,
                REMOVE_COUNT=0,
                DOWNLOAD_SIZE=0,
                UPLOAD_SIZE=0,
                STATE=item.get('state'),
                LST_MOD_DATE=time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time())),
                SENDMESSAGE=item.get('sendmessage')
            ))
        else:
            self._db.query(SITEBRUSHTASK).filter(SITEBRUSHTASK.ID == int(brush_id)).update({
                "NAME": item.get('name'),
                "SITE": item.get('site'),
                "FREELEECH": item.get('free'),
                "RSS_RULE": json.dumps(item.get('rss_rule'), ensure_ascii=False),
                "REMOVE_RULE": json.dumps(item.get('remove_rule'), ensure_ascii=False),
                "STOP_RULE": json.dumps(item.get('stop_rule'), ensure_ascii=False),
                "SEED_SIZE": item.get('seed_size'),
                "TIME_RANGE": item.get('time_range'),
                "RSSURL": item.get('rssurl'),
                "INTEVAL": item.get('interval'),
                "DOWNLOADER": item.get('downloader'),
                "LABEL": item.get('label'),
                "SAVEPATH": item.get('savepath'),
                "TRANSFER": item.get('transfer'),
                "STATE": item.get('state'),
                "LST_MOD_DATE": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time())),
                "SENDMESSAGE": item.get('sendmessage')
            })

    @DbPersist(BaseRepository._db)
    def delete_brushtask(self, brush_id):
        """
        删除刷流任务
        """
        self._db.query(SITEBRUSHTASK).filter(SITEBRUSHTASK.ID == int(brush_id)).delete()
        self._db.query(SITEBRUSHTORRENTS).filter(SITEBRUSHTORRENTS.TASK_ID == brush_id).delete()

    def get_brushtasks(self, brush_id=None):
        """
        查询刷流任务
        """
        if brush_id:
            return self._db.query(SITEBRUSHTASK).filter(SITEBRUSHTASK.ID == int(brush_id)).first()
        else:
            return self._db.query(SITEBRUSHTASK) \
                .join(CONFIGSITE, SITEBRUSHTASK.SITE == CONFIGSITE.ID) \
                .order_by(cast(CONFIGSITE.PRI, Integer).asc()).all()

    def get_brushtask_totalsize(self, brush_id):
        """
        查询刷流任务总体积
        """
        if not brush_id:
            return 0
        ret = self._db.query(func.sum(cast(SITEBRUSHTORRENTS.TORRENT_SIZE, Integer))).filter(
            SITEBRUSHTORRENTS.TASK_ID == brush_id,
            SITEBRUSHTORRENTS.DOWNLOAD_ID != '0',
            SITEBRUSHTORRENTS.TORRENT_SIZE != '',
            SITEBRUSHTORRENTS.TORRENT_SIZE.isnot(None)
        ).first()
        return ret[0] or 0 if ret else 0

    @DbPersist(BaseRepository._db)
    def update_brushtask_state(self, state, tid=None):
        """
        改变刷流任务的状态
        """
        if tid:
            self._db.query(SITEBRUSHTASK).filter(SITEBRUSHTASK.ID == int(tid)).update({
                "STATE": "Y" if state == "Y" else "N"
            })
        else:
            self._db.query(SITEBRUSHTASK).update({
                "STATE": "Y" if state == "Y" else "N"
            })

    @DbPersist(BaseRepository._db)
    def add_brushtask_download_count(self, brush_id):
        """
        增加刷流下载数
        """
        if not brush_id:
            return
        self._db.query(SITEBRUSHTASK).filter(SITEBRUSHTASK.ID == int(brush_id)).update({
            "DOWNLOAD_COUNT": SITEBRUSHTASK.DOWNLOAD_COUNT + 1,
            "LST_MOD_DATE": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))
        })

    def get_brushtask_remove_size(self, brush_id):
        """
        获取已删除种子的上传量
        """
        if not brush_id:
            return 0
        return self._db.query(SITEBRUSHTORRENTS.TORRENT_SIZE).filter(
            SITEBRUSHTORRENTS.TASK_ID == brush_id,
            SITEBRUSHTORRENTS.DOWNLOAD_ID == '0'
        ).all()

    @DbPersist(BaseRepository._db)
    def add_brushtask_upload_count(self, brush_id, upload_size, download_size, remove_count):
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

        self._db.query(SITEBRUSHTASK).filter(SITEBRUSHTASK.ID == int(brush_id)).update({
            "REMOVE_COUNT": SITEBRUSHTASK.REMOVE_COUNT + remove_count,
            "UPLOAD_SIZE": int(upload_size) + delete_upsize,
            "DOWNLOAD_SIZE": int(download_size) + delete_dlsize,
        })

    @DbPersist(BaseRepository._db)
    def insert_brushtask_torrent(self, brush_id, title, enclosure, downloader, download_id, size):
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

        self._db.insert(SITEBRUSHTORRENTS(
            TASK_ID=brush_id,
            TORRENT_NAME=title,
            TORRENT_SIZE=size,
            ENCLOSURE=enclosure,
            DOWNLOADER=downloader,
            DOWNLOAD_ID=download_id,
            LST_MOD_DATE=time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))
        ))

    def get_brushtask_torrents(self, brush_id, active=True):
        """
        查询刷流任务所有种子
        """
        if not brush_id:
            return []
        if active:
            return self._db.query(SITEBRUSHTORRENTS).filter(
                SITEBRUSHTORRENTS.TASK_ID == int(brush_id),
                SITEBRUSHTORRENTS.DOWNLOAD_ID != '0'
            ).all()
        else:
            return self._db.query(SITEBRUSHTORRENTS).filter(
                SITEBRUSHTORRENTS.TASK_ID == int(brush_id)
            ).order_by(SITEBRUSHTORRENTS.LST_MOD_DATE.desc()).all()

    def get_brushtask_torrent_by_enclosure(self, enclosure):
        """
        根据URL查询刷流任务种子
        """
        from app.utils import StringUtils
        from app.sites.engine import SiteEngine

        if not enclosure:
            return None

        engine = SiteEngine.get_instance()
        if engine.is_tid_based_dedup(enclosure):
            tid = StringUtils.get_tid_by_url(enclosure)
            domain = engine.normalize_domain(enclosure)
            all_torrents = self._db.query(SITEBRUSHTORRENTS).filter(
                SITEBRUSHTORRENTS.ENCLOSURE.like(f"%{domain}%")
            ).all()
            return list(filter(lambda t: StringUtils.get_tid_by_url(t.ENCLOSURE) == tid, all_torrents))

        return self._db.query(SITEBRUSHTORRENTS).filter(SITEBRUSHTORRENTS.ENCLOSURE == enclosure).first()

    def is_brushtask_torrent_exists(self, brush_id, title, enclosure):
        """
        查询刷流任务种子是否已存在
        """
        if not brush_id:
            return False
        count = self._db.query(SITEBRUSHTORRENTS).filter(
            SITEBRUSHTORRENTS.TASK_ID == brush_id,
            SITEBRUSHTORRENTS.TORRENT_NAME == title,
            SITEBRUSHTORRENTS.ENCLOSURE == enclosure
        ).count()
        return count > 0

    @DbPersist(BaseRepository._db)
    def update_brushtask_torrent_state(self, ids: list):
        """
        更新刷流种子的状态
        """
        if not ids:
            return
        for _id in ids:
            self._db.query(SITEBRUSHTORRENTS).filter(
                SITEBRUSHTORRENTS.TASK_ID == _id[1],
                SITEBRUSHTORRENTS.DOWNLOAD_ID == _id[2]
            ).update({
                "TORRENT_SIZE": _id[0],
                "DOWNLOAD_ID": '0'
            })

    @DbPersist(BaseRepository._db)
    def delete_brushtask_torrent(self, brush_id, download_id):
        """
        删除刷流种子记录
        """
        if not download_id or not brush_id:
            return
        self._db.query(SITEBRUSHTORRENTS).filter(
            SITEBRUSHTORRENTS.TASK_ID == brush_id,
            SITEBRUSHTORRENTS.DOWNLOAD_ID == download_id
        ).delete()

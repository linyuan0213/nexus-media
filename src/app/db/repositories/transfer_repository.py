"""
Transfer Repository
Handles transfer history and unrecognized transfer related database operations.
"""

import datetime
import os.path
import time
from enum import Enum

from sqlalchemy import func

from app.db.transaction import auto_commit
from app.db.models import SYNCHISTORY, TRANSFERBLACKLIST, TRANSFERHISTORY, TRANSFERUNKNOWN
from app.db.repositories.base_repository import BaseRepository
from app.schemas.media import TransferMediaDTO


class TransferRepository(BaseRepository):
    """
    转移历史仓储
    处理转移历史、未识别记录和黑名单的数据库操作
    """

    # ==================== Transfer History ====================

    def is_transfer_history_exists(
        self, source_path: str, source_filename: str, dest_path: str, dest_filename: str
    ) -> bool:
        """
        查询识别转移记录是否存在
        """
        if not source_path or not source_filename or not dest_path or not dest_filename:
            return False
        ret = (
            self._db.query(TRANSFERHISTORY)
            .filter(
                source_path == TRANSFERHISTORY.SOURCE_PATH,
                source_filename == TRANSFERHISTORY.SOURCE_FILENAME,
                dest_path == TRANSFERHISTORY.DEST_PATH,
                dest_filename == TRANSFERHISTORY.DEST_FILENAME,
            )
            .count()
        )
        return ret > 0

    @auto_commit(BaseRepository._db)
    def update_transfer_history_date(
        self, source_path: str, source_filename: str, dest_path: str, dest_filename: str, date: str
    ) -> None:
        """
        更新历史转移记录时间
        """
        self._db.query(TRANSFERHISTORY).filter(
            source_path == TRANSFERHISTORY.SOURCE_PATH,
            source_filename == TRANSFERHISTORY.SOURCE_FILENAME,
            dest_path == TRANSFERHISTORY.DEST_PATH,
            dest_filename == TRANSFERHISTORY.DEST_FILENAME,
        ).update({"DATE": date})

    @auto_commit(BaseRepository._db)
    def insert_transfer_history(
        self,
        in_from: Enum,
        rmt_mode: str,
        in_path: str,
        out_path: str,
        dest: str,
        media_info: TransferMediaDTO,
        dst_backend: str | None = None,
    ) -> None:
        """
        插入识别转移记录
        """
        if not media_info:
            return

        if in_path:
            in_path = os.path.normpath(in_path)
            source_path = os.path.dirname(in_path)
            source_filename = os.path.basename(in_path)
        else:
            return

        if out_path:
            outpath = os.path.normpath(out_path)
            dest_path = os.path.dirname(outpath)
            dest_filename = os.path.basename(outpath)
            season_episode = media_info.season_episode
        else:
            dest_path = ""
            dest_filename = ""
            season_episode = media_info.season_episode

        title = media_info.title
        timestr = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time()))

        if self.is_transfer_history_exists(source_path, source_filename, dest_path, dest_filename):
            self.update_transfer_history_date(source_path, source_filename, dest_path, dest_filename, timestr)
            return

        dest = dest or ""
        mode_value = rmt_mode or ""
        self._db.insert(
            TRANSFERHISTORY(
                MODE=mode_value,
                TYPE=media_info.type_value,
                CATEGORY=media_info.category,
                TMDBID=int(media_info.tmdb_id),
                TITLE=title,
                YEAR=media_info.year,
                SEASON_EPISODE=season_episode,
                SOURCE=str(in_from.value),
                SOURCE_PATH=source_path,
                SOURCE_FILENAME=source_filename,
                DEST=dest,
                DEST_PATH=dest_path,
                DEST_FILENAME=dest_filename,
                DST_BACKEND=dst_backend or "local",
                DATE=timestr,
            )
        )

    def get_transfer_history(self, search: str | None, page: int, rownum: int) -> tuple[int, list[TRANSFERHISTORY]]:
        """
        查询识别转移记录（分页）
        """
        if int(page) == 1:
            begin_pos = 0
        else:
            begin_pos = (int(page) - 1) * int(rownum)

        if search:
            search = f"%{search}%"
            count = (
                self._db.query(TRANSFERHISTORY)
                .filter((TRANSFERHISTORY.SOURCE_FILENAME.like(search)) | (TRANSFERHISTORY.TITLE.like(search)))
                .count()
            )
            data = (
                self._db.query(TRANSFERHISTORY)
                .filter((TRANSFERHISTORY.SOURCE_FILENAME.like(search)) | (TRANSFERHISTORY.TITLE.like(search)))
                .order_by(TRANSFERHISTORY.DATE.desc())
                .limit(int(rownum))
                .offset(begin_pos)
                .all()
            )
            return count, data
        else:
            return self._db.query(TRANSFERHISTORY).count(), self._db.query(TRANSFERHISTORY).order_by(
                TRANSFERHISTORY.DATE.desc()
            ).limit(int(rownum)).offset(begin_pos).all()

    def get_transfer_info_by_id(self, logid: int | None) -> TRANSFERHISTORY | None:
        """
        据logid查询PATH
        """
        return self._db.query(TRANSFERHISTORY).filter(int(logid or 0) == TRANSFERHISTORY.ID).first()

    def get_transfer_info_by(
        self, tmdbid: int | None, season: str | None = None, season_episode: str | None = None
    ) -> list[TRANSFERHISTORY] | None:
        """
        据tmdbid、season、season_episode查询转移记录
        """
        if tmdbid and not season and not season_episode:
            return self._db.query(TRANSFERHISTORY).filter(int(tmdbid) == TRANSFERHISTORY.TMDBID).all()
        if tmdbid and season:
            season = f"%{season}%"
            return (
                self._db.query(TRANSFERHISTORY)
                .filter(int(tmdbid) == TRANSFERHISTORY.TMDBID, TRANSFERHISTORY.SEASON_EPISODE.like(season))
                .all()
            )
        if tmdbid and season_episode:
            return (
                self._db.query(TRANSFERHISTORY)
                .filter(int(tmdbid) == TRANSFERHISTORY.TMDBID, season_episode == TRANSFERHISTORY.SEASON_EPISODE)
                .all()
            )

    @auto_commit(BaseRepository._db)
    def delete_transfer_history_by_source(self, source_path: str, source_filename: str) -> None:
        self._db.query(TRANSFERHISTORY).filter(
            source_path == TRANSFERHISTORY.SOURCE_PATH,
            source_filename == TRANSFERHISTORY.SOURCE_FILENAME,
        ).delete()

    def is_transfer_history_exists_by_source_full_path(self, source_full_path: str) -> bool:
        """
        据源文件的全路径查询识别转移记录
        """
        path = os.path.dirname(source_full_path)
        filename = os.path.basename(source_full_path)
        ret = (
            self._db.query(TRANSFERHISTORY)
            .filter(path == TRANSFERHISTORY.SOURCE_PATH, filename == TRANSFERHISTORY.SOURCE_FILENAME)
            .count()
        )
        return ret > 0

    @auto_commit(BaseRepository._db)
    def delete_transfer_log_by_id(self, logid: int) -> None:
        """
        根据logid删除记录
        """
        self._db.query(TRANSFERHISTORY).filter(int(logid) == TRANSFERHISTORY.ID).delete()

    @auto_commit(BaseRepository._db)
    def delete_transfer(self) -> None:
        """
        删除所有识别记录
        """
        self._db.query(TRANSFERHISTORY).delete()

    def get_transfer_statistics(self, days: int = 30) -> list[tuple]:
        """
        查询历史记录统计
        使用 func.substring 替代 func.substr 以支持多种数据库
        days <= 0 表示查询全部
        """
        date_str = func.substr(TRANSFERHISTORY.DATE, 1, 10).label("date_str")
        query = self._db.query(TRANSFERHISTORY.TYPE, date_str, func.count("*"))
        if days > 0:
            begin_date = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
            query = query.filter(begin_date < TRANSFERHISTORY.DATE)
        return query.group_by(TRANSFERHISTORY.TYPE, date_str).order_by(date_str).all()

    # ==================== Transfer Unknown ====================

    def get_transfer_unknowns(self) -> list[TRANSFERUNKNOWN]:
        return self.get_transfer_unknown_paths()

    def get_transfer_unknown_paths(self) -> list[TRANSFERUNKNOWN]:
        """
        查询未识别的记录列表
        """
        return self._db.query(TRANSFERUNKNOWN).filter(TRANSFERUNKNOWN.STATE == "N").all()

    def get_transfer_unknown_paths_by_page(
        self, search: str | None, page: int, rownum: int
    ) -> tuple[int, list[TRANSFERUNKNOWN]]:
        """
        按页查询未识别的记录列表
        """
        if int(page) == 1:
            begin_pos = 0
        else:
            begin_pos = (int(page) - 1) * int(rownum)

        if search:
            search = f"%{search}%"
            count = (
                self._db.query(TRANSFERUNKNOWN)
                .filter((TRANSFERUNKNOWN.STATE == "N") & (TRANSFERUNKNOWN.PATH.like(search)))
                .count()
            )
            data = (
                self._db.query(TRANSFERUNKNOWN)
                .filter((TRANSFERUNKNOWN.STATE == "N") & (TRANSFERUNKNOWN.PATH.like(search)))
                .order_by(TRANSFERUNKNOWN.ID.desc())
                .limit(int(rownum))
                .offset(begin_pos)
                .all()
            )
            return count, data
        else:
            return self._db.query(TRANSFERUNKNOWN).filter(TRANSFERUNKNOWN.STATE == "N").count(), self._db.query(
                TRANSFERUNKNOWN
            ).filter(TRANSFERUNKNOWN.STATE == "N").order_by(TRANSFERUNKNOWN.ID.desc()).limit(int(rownum)).offset(
                begin_pos
            ).all()

    @auto_commit(BaseRepository._db)
    def update_transfer_unknown_state(self, path: str) -> None:
        """
        更新未识别记录为识别
        """
        if not path:
            return
        self._db.query(TRANSFERUNKNOWN).filter(os.path.normpath(path) == TRANSFERUNKNOWN.PATH).update({"STATE": "Y"})

    @auto_commit(BaseRepository._db)
    def delete_transfer_unknown(self, tid: int | None) -> None:
        """
        删除未识别记录
        """
        if not tid:
            return
        self._db.query(TRANSFERUNKNOWN).filter(int(tid) == TRANSFERUNKNOWN.ID).delete()

    def get_transfer_unknown_by_id(self, tid: int | None) -> TRANSFERUNKNOWN | None:
        return self.get_unknown_info_by_id(tid)

    def get_unknown_info_by_id(self, tid: int | None) -> TRANSFERUNKNOWN | None:
        """
        查询未识别记录
        """
        if not tid:
            return None
        return self._db.query(TRANSFERUNKNOWN).filter(int(tid) == TRANSFERUNKNOWN.ID).first()

    def get_transfer_unknown_by_path(self, path: str) -> list[TRANSFERUNKNOWN]:
        """
        根据路径查询未识别记录
        """
        if not path:
            return []
        return self._db.query(TRANSFERUNKNOWN).filter(os.path.normpath(path) == TRANSFERUNKNOWN.PATH).all()

    def is_exists_transfer_unknowns(self, path: str) -> bool:
        return self.is_transfer_unknown_exists(path)

    def is_transfer_unknown_exists(self, path: str) -> bool:
        """
        查询未识别记录是否存在
        """
        if not path:
            return False
        ret = self._db.query(TRANSFERUNKNOWN).filter(os.path.normpath(path) == TRANSFERUNKNOWN.PATH).count()
        return ret > 0

    def is_need_insert_transfer_unknown(self, path: str) -> bool:
        """
        检查是否需要插入未识别记录
        """
        if not path:
            return False
        unknowns = self.get_transfer_unknown_by_path(path)
        if unknowns:
            is_all_proceed = True
            for unknown in unknowns:
                if str(unknown.STATE or "") == "N":
                    is_all_proceed = False
                    break
            if is_all_proceed:
                is_transfer_history_exists = self.is_transfer_history_exists_by_source_full_path(path)
                if is_transfer_history_exists:
                    return False
                else:
                    for unknown in unknowns:
                        self.delete_transfer_unknown(int(str(unknown.ID)))
                    return True
            else:
                return True
        else:
            return True

    @auto_commit(BaseRepository._db)
    def insert_transfer_unknown(self, path: str, dest: str, rmt_mode: str) -> None:
        """
        插入未识别记录
        """
        if not path:
            return
        if self.is_transfer_unknown_exists(path):
            return
        path = os.path.normpath(path)
        if dest:
            dest = os.path.normpath(dest)
        else:
            dest = ""
        self._db.insert(TRANSFERUNKNOWN(PATH=path, DEST=dest, STATE="N", MODE=rmt_mode or ""))

    def is_transfer_in_blacklist(self, path: str) -> bool:
        """
        查询是否为黑名单
        """
        if not path:
            return False
        ret = self._db.query(TRANSFERBLACKLIST).filter(os.path.normpath(path) == TRANSFERBLACKLIST.PATH).count()
        return ret > 0

    def is_exists_transfer_blacklist(self, path: str) -> bool:
        return self.is_transfer_in_blacklist(path)

    def is_transfer_notin_blacklist(self, path: str) -> bool:
        """
        查询是否不在黑名单
        """
        return not self.is_transfer_in_blacklist(path)

    @auto_commit(BaseRepository._db)
    def truncate_transfer_unknowns(self) -> None:
        self._db.query(TRANSFERUNKNOWN).delete()

    @auto_commit(BaseRepository._db)
    def insert_transfer_blacklist(self, path: str) -> None:
        """
        插入黑名单记录
        """
        self._db.insert(TRANSFERBLACKLIST(PATH=os.path.normpath(path)))

    def delete_transfer_blacklist(self, path: str) -> None:
        """
        删除黑名单记录
        """
        self._db.query(TRANSFERBLACKLIST).filter(str(path) == TRANSFERBLACKLIST.PATH).delete()
        self._db.query(SYNCHISTORY).filter(str(path) == SYNCHISTORY.PATH).delete()

    @auto_commit(BaseRepository._db)
    def truncate_transfer_blacklist(self) -> None:
        """
        清空黑名单记录
        """
        self._db.query(TRANSFERBLACKLIST).delete()
        self._db.query(SYNCHISTORY).delete()

    # ==================== Sync History ====================

    def is_sync_in_history(self, path: str, dest: str) -> bool:
        """
        查询是否存在同步历史记录
        """
        if not path:
            return False
        count = (
            self._db.query(SYNCHISTORY)
            .filter(os.path.normpath(path) == SYNCHISTORY.PATH, os.path.normpath(dest) == SYNCHISTORY.DEST)
            .count()
        )
        return count > 0

    @auto_commit(BaseRepository._db)
    def insert_sync_history(self, path: str, src: str, dest: str) -> None:
        """
        插入同步历史记录
        """
        if not path or not dest:
            return
        if self.is_sync_in_history(path, dest):
            return

        self._db.insert(
            SYNCHISTORY(PATH=os.path.normpath(path), SRC=os.path.normpath(src), DEST=os.path.normpath(dest))
        )

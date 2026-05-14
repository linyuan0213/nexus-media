"""
Word Repository
Handles custom words and word groups related database operations.
"""

from app.db import DbPersist
from app.db.models import CUSTOMWORDGROUPS, CUSTOMWORDS
from app.db.repositories.base_repository import BaseRepository


class WordRepository(BaseRepository):
    """
    自定义识别词仓储
    处理自定义识别词和词组的数据库操作
    """

    # ==================== Custom Words ====================

    @DbPersist(BaseRepository._db)
    def insert_custom_word(
        self, replaced, replace, front, back, offset, wtype, gid, season, enabled, regex, whelp, note=None
    ):
        """
        增加自定义识别词

        Args:
            replaced: 被替换的词
            replace: 替换为的词
            front: 前置词
            back: 后置词
            offset: 偏移量
            wtype: 类型
            gid: 组ID
            season: 季
            enabled: 是否启用
            regex: 是否正则
            whelp: 帮助信息
            note: 备注
        """
        self._db.insert(
            CUSTOMWORDS(
                REPLACED=replaced,
                REPLACE=replace,
                FRONT=front,
                BACK=back,
                OFFSET=offset,
                TYPE=int(wtype),
                GROUP_ID=int(gid),
                SEASON=int(season),
                ENABLED=int(enabled),
                REGEX=int(regex),
                HELP=whelp,
                NOTE=note,
            )
        )

    @DbPersist(BaseRepository._db)
    def delete_custom_word(self, wid=None):
        """
        删除自定义识别词

        Args:
            wid: 词ID，None则删除所有
        """
        if not wid:
            self._db.query(CUSTOMWORDS).delete()
        self._db.query(CUSTOMWORDS).filter(int(wid or 0) == CUSTOMWORDS.ID).delete()

    @DbPersist(BaseRepository._db)
    def check_custom_word(self, wid=None, enabled=None):
        """
        设置自定义识别词状态

        Args:
            wid: 词ID，None则更新所有
            enabled: 是否启用
        """
        if enabled is None:
            return
        if wid:
            self._db.query(CUSTOMWORDS).filter(int(wid) == CUSTOMWORDS.ID).update({"ENABLED": int(enabled)})
        else:
            self._db.query(CUSTOMWORDS).update({"ENABLED": int(enabled)})

    def get_custom_words(self, wid=None, gid=None, enabled=None):
        """
        查询自定义识别词

        Args:
            wid: 词ID
            gid: 组ID
            enabled: 是否启用

        Returns:
            自定义识别词列表
        """
        if wid:
            return self._db.query(CUSTOMWORDS).filter(int(wid) == CUSTOMWORDS.ID).all()
        elif gid:
            return (
                self._db.query(CUSTOMWORDS)
                .filter(int(gid) == CUSTOMWORDS.GROUP_ID)
                .order_by(CUSTOMWORDS.ENABLED.desc(), CUSTOMWORDS.TYPE, CUSTOMWORDS.REGEX, CUSTOMWORDS.ID)
                .all()
            )
        elif enabled is not None:
            return (
                self._db.query(CUSTOMWORDS)
                .filter(int(enabled) == CUSTOMWORDS.ENABLED)
                .order_by(CUSTOMWORDS.GROUP_ID, CUSTOMWORDS.TYPE, CUSTOMWORDS.REGEX, CUSTOMWORDS.ID)
                .all()
            )
        return (
            self._db.query(CUSTOMWORDS)
            .order_by(
                CUSTOMWORDS.GROUP_ID, CUSTOMWORDS.ENABLED.desc(), CUSTOMWORDS.TYPE, CUSTOMWORDS.REGEX, CUSTOMWORDS.ID
            )
            .all()
        )

    def is_custom_words_existed(self, replaced=None, front=None, back=None):
        """
        查询自定义识别词是否存在

        Args:
            replaced: 被替换的词
            front: 前置词
            back: 后置词

        Returns:
            是否存在
        """
        if replaced:
            count = self._db.query(CUSTOMWORDS).filter(replaced == CUSTOMWORDS.REPLACED).count()
        elif front and back:
            count = self._db.query(CUSTOMWORDS).filter(front == CUSTOMWORDS.FRONT, back == CUSTOMWORDS.BACK).count()
        else:
            return False
        return count > 0

    # ==================== Custom Word Groups ====================

    @DbPersist(BaseRepository._db)
    def insert_custom_word_groups(self, title, year, gtype, tmdbid, season_count, note=None):
        """
        增加自定义识别词组

        Args:
            title: 标题
            year: 年份
            gtype: 类型
            tmdbid: TMDB ID
            season_count: 季数
            note: 备注
        """
        self._db.insert(
            CUSTOMWORDGROUPS(
                TITLE=title, YEAR=year, TYPE=int(gtype), TMDBID=int(tmdbid), SEASON_COUNT=int(season_count), NOTE=note
            )
        )

    @DbPersist(BaseRepository._db)
    def delete_custom_word_group(self, gid):
        """
        删除自定义识别词组

        Args:
            gid: 组ID
        """
        if not gid:
            return
        self._db.query(CUSTOMWORDS).filter(int(gid) == CUSTOMWORDS.GROUP_ID).delete()
        self._db.query(CUSTOMWORDGROUPS).filter(int(gid) == CUSTOMWORDGROUPS.ID).delete()

    def get_custom_word_groups(self, gid=None, tmdbid=None, gtype=None):
        """
        查询自定义识别词组

        Args:
            gid: 组ID
            tmdbid: TMDB ID
            gtype: 类型

        Returns:
            自定义识别词组列表
        """
        if gid:
            return self._db.query(CUSTOMWORDGROUPS).filter(int(gid) == CUSTOMWORDGROUPS.ID).all()
        if tmdbid and gtype:
            return (
                self._db.query(CUSTOMWORDGROUPS)
                .filter(int(tmdbid) == CUSTOMWORDGROUPS.TMDBID, int(gtype) == CUSTOMWORDGROUPS.TYPE)
                .all()
            )
        if tmdbid:
            return self._db.query(CUSTOMWORDGROUPS).filter(int(tmdbid) == CUSTOMWORDGROUPS.TMDBID).all()
        return self._db.query(CUSTOMWORDGROUPS).all()

    def is_custom_word_group_existed(self, tmdbid=None, gtype=None):
        """
        查询自定义识别词组是否存在

        Args:
            tmdbid: TMDB ID
            gtype: 类型

        Returns:
            是否存在
        """
        if not gtype or not tmdbid:
            return False
        count = (
            self._db.query(CUSTOMWORDGROUPS)
            .filter(int(tmdbid) == CUSTOMWORDGROUPS.TMDBID, int(gtype) == CUSTOMWORDGROUPS.TYPE)
            .count()
        )
        return count > 0

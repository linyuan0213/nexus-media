"""
自定义识别词仓储接口
"""
from typing import Protocol

from app.domain.entities.word import CustomWordEntity, CustomWordGroupEntity


class ICustomWordRepository(Protocol):
    """自定义识别词仓储接口"""

    def get_custom_words(self, wid: int | None = None, gid: int | None = None,
                         enabled: int | None = None) -> list[CustomWordEntity]:
        """查询自定义识别词"""
        ...

    def is_custom_words_existed(self, replaced: str | None = None,
                                 front: str | None = None, back: str | None = None) -> bool:
        """查询自定义识别词是否存在"""
        ...

    def insert_custom_word(self, replaced: str, replace: str, front: str, back: str,
                           offset: str, wtype: int, gid: int, season: int,
                           enabled: int, regex: int, whelp: str, note: str | None = None) -> bool:
        """增加自定义识别词"""
        ...

    def delete_custom_word(self, wid: int | None = None) -> bool:
        """删除自定义识别词"""
        ...

    def check_custom_word(self, wid: int | None = None, enabled: int | None = None) -> bool:
        """设置自定义识别词状态"""
        ...


class ICustomWordGroupRepository(Protocol):
    """自定义识别词组仓储接口"""

    def get_custom_word_groups(self, gid: int | None = None,
                                tmdbid: int | None = None, gtype: int | None = None) -> list[CustomWordGroupEntity]:
        """查询自定义识别词组"""
        ...

    def is_custom_word_group_existed(self, tmdbid: int | None = None,
                                      gtype: int | None = None) -> bool:
        """查询自定义识别词组是否存在"""
        ...

    def insert_custom_word_groups(self, title: str, year: str, gtype: int,
                                   tmdbid: int, season_count: int, note: str | None = None) -> bool:
        """增加自定义识别词组"""
        ...

    def delete_custom_word_group(self, gid: int) -> bool:
        """删除自定义识别词组"""
        ...

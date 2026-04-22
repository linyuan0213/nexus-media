# -*- coding: utf-8 -*-
"""
自定义识别词仓储接口
"""
from typing import List, Optional, Protocol

from app.domain.entities.word import CustomWordEntity, CustomWordGroupEntity


class ICustomWordRepository(Protocol):
    """自定义识别词仓储接口"""

    def get_custom_words(self, wid: Optional[int] = None, gid: Optional[int] = None,
                         enabled: Optional[int] = None) -> List[CustomWordEntity]:
        """查询自定义识别词"""
        ...

    def is_custom_words_existed(self, replaced: Optional[str] = None,
                                 front: Optional[str] = None, back: Optional[str] = None) -> bool:
        """查询自定义识别词是否存在"""
        ...

    def insert_custom_word(self, replaced: str, replace: str, front: str, back: str,
                           offset: str, wtype: int, gid: int, season: int,
                           enabled: int, regex: int, whelp: str, note: Optional[str] = None) -> bool:
        """增加自定义识别词"""
        ...

    def delete_custom_word(self, wid: Optional[int] = None) -> bool:
        """删除自定义识别词"""
        ...

    def check_custom_word(self, wid: Optional[int] = None, enabled: Optional[int] = None) -> bool:
        """设置自定义识别词状态"""
        ...


class ICustomWordGroupRepository(Protocol):
    """自定义识别词组仓储接口"""

    def get_custom_word_groups(self, gid: Optional[int] = None,
                                tmdbid: Optional[int] = None, gtype: Optional[int] = None) -> List[CustomWordGroupEntity]:
        """查询自定义识别词组"""
        ...

    def is_custom_word_group_existed(self, tmdbid: Optional[int] = None,
                                      gtype: Optional[int] = None) -> bool:
        """查询自定义识别词组是否存在"""
        ...

    def insert_custom_word_groups(self, title: str, year: str, gtype: int,
                                   tmdbid: int, season_count: int, note: Optional[str] = None) -> bool:
        """增加自定义识别词组"""
        ...

    def delete_custom_word_group(self, gid: int) -> bool:
        """删除自定义识别词组"""
        ...

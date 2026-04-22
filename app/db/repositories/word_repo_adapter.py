# -*- coding: utf-8 -*-
"""
自定义识别词领域 Repository 适配器
将旧版 WordRepository 适配为新领域接口
"""
from typing import List, Optional

from app.domain.entities.word import CustomWordEntity, CustomWordGroupEntity
from app.domain.interfaces.word_repo import ICustomWordRepository, ICustomWordGroupRepository
from app.db.repositories.word_repository import WordRepository


class CustomWordRepositoryAdapter(ICustomWordRepository):
    """自定义识别词仓储适配器"""

    def __init__(self, repo: Optional[WordRepository] = None):
        self._repo = repo or WordRepository()

    def get_custom_words(self, wid: Optional[int] = None, gid: Optional[int] = None,
                         enabled: Optional[int] = None) -> List[CustomWordEntity]:
        rows = self._repo.get_custom_words(wid=wid, gid=gid, enabled=enabled)
        return [e for e in [CustomWordEntity.from_orm(r) for r in rows] if e is not None]

    def is_custom_words_existed(self, replaced: Optional[str] = None,
                                 front: Optional[str] = None, back: Optional[str] = None) -> bool:
        return self._repo.is_custom_words_existed(replaced=replaced, front=front, back=back)

    def insert_custom_word(self, replaced: str, replace: str, front: str, back: str,
                           offset: str, wtype: int, gid: int, season: int,
                           enabled: int, regex: int, whelp: str, note: Optional[str] = None) -> bool:
        return self._repo.insert_custom_word(replaced, replace, front, back, offset,
                                              wtype, gid, season, enabled, regex, whelp, note)

    def delete_custom_word(self, wid: Optional[int] = None) -> bool:
        return self._repo.delete_custom_word(wid=wid)

    def check_custom_word(self, wid: Optional[int] = None, enabled: Optional[int] = None) -> bool:
        return self._repo.check_custom_word(wid=wid, enabled=enabled)


class CustomWordGroupRepositoryAdapter(ICustomWordGroupRepository):
    """自定义识别词组仓储适配器"""

    def __init__(self, repo: Optional[WordRepository] = None):
        self._repo = repo or WordRepository()

    def get_custom_word_groups(self, gid: Optional[int] = None,
                                tmdbid: Optional[int] = None, gtype: Optional[int] = None) -> List[CustomWordGroupEntity]:
        rows = self._repo.get_custom_word_groups(gid=gid, tmdbid=tmdbid, gtype=gtype)
        return [e for e in [CustomWordGroupEntity.from_orm(r) for r in rows] if e is not None]

    def is_custom_word_group_existed(self, tmdbid: Optional[int] = None,
                                      gtype: Optional[int] = None) -> bool:
        return self._repo.is_custom_word_group_existed(tmdbid=tmdbid, gtype=gtype)

    def insert_custom_word_groups(self, title: str, year: str, gtype: int,
                                   tmdbid: int, season_count: int, note: Optional[str] = None) -> bool:
        return self._repo.insert_custom_word_groups(title, year, gtype, tmdbid, season_count, note)

    def delete_custom_word_group(self, gid: int) -> bool:
        return self._repo.delete_custom_word_group(gid=gid)

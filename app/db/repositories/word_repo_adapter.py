"""
自定义识别词领域 Repository 适配器
将旧版 WordRepository 适配为新领域接口
"""

from app.db.repositories.word_repository import WordRepository
from app.domain.entities.word import CustomWordEntity, CustomWordGroupEntity
from app.domain.interfaces.word_repo import ICustomWordGroupRepository, ICustomWordRepository


class CustomWordRepositoryAdapter(ICustomWordRepository):
    """自定义识别词仓储适配器"""

    def __init__(self, repo: WordRepository | None = None):
        self._repo = repo or WordRepository()

    def get_custom_words(
        self, wid: int | None = None, gid: int | None = None, enabled: int | None = None
    ) -> list[CustomWordEntity]:
        rows = self._repo.get_custom_words(wid=wid, gid=gid, enabled=enabled)
        return [e for e in [CustomWordEntity.from_orm(r) for r in rows] if e is not None]

    def is_custom_words_existed(
        self, replaced: str | None = None, front: str | None = None, back: str | None = None
    ) -> bool:
        return self._repo.is_custom_words_existed(replaced=replaced, front=front, back=back)

    def insert_custom_word(
        self,
        replaced: str,
        replace: str,
        front: str,
        back: str,
        offset: str,
        wtype: int,
        gid: int,
        season: int,
        enabled: int,
        regex: int,
        whelp: str,
        note: str | None = None,
    ) -> bool:
        return self._repo.insert_custom_word(
            replaced, replace, front, back, offset, wtype, gid, season, enabled, regex, whelp, note
        )

    def delete_custom_word(self, wid: int | None = None) -> bool:
        return self._repo.delete_custom_word(wid=wid)

    def check_custom_word(self, wid: int | None = None, enabled: int | None = None) -> bool:
        return self._repo.check_custom_word(wid=wid, enabled=enabled)


class CustomWordGroupRepositoryAdapter(ICustomWordGroupRepository):
    """自定义识别词组仓储适配器"""

    def __init__(self, repo: WordRepository | None = None):
        self._repo = repo or WordRepository()

    def get_custom_word_groups(
        self, gid: int | None = None, tmdbid: int | None = None, gtype: int | None = None
    ) -> list[CustomWordGroupEntity]:
        rows = self._repo.get_custom_word_groups(gid=gid, tmdbid=tmdbid, gtype=gtype)
        return [e for e in [CustomWordGroupEntity.from_orm(r) for r in rows] if e is not None]

    def is_custom_word_group_existed(self, tmdbid: int | None = None, gtype: int | None = None) -> bool:
        return self._repo.is_custom_word_group_existed(tmdbid=tmdbid, gtype=gtype)

    def insert_custom_word_groups(
        self, title: str, year: str, gtype: int, tmdbid: int, season_count: int, note: str | None = None
    ) -> bool:
        return self._repo.insert_custom_word_groups(title, year, gtype, tmdbid, season_count, note)

    def delete_custom_word_group(self, gid: int) -> bool:
        return self._repo.delete_custom_word_group(gid=gid)

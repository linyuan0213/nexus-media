# -*- coding: utf-8 -*-
"""
转移领域 Repository 适配器
"""
from typing import List, Optional, Tuple

from app.domain.entities.transfer import (
    TransferBlacklistEntity,
    TransferHistoryEntity,
    TransferUnknownEntity,
)
from app.db.repositories.transfer_repository import TransferRepository


class TransferHistoryRepositoryAdapter:
    def __init__(self, repo: Optional[TransferRepository] = None):
        self._repo = repo or TransferRepository()

    def is_exists(self, source_path: str, source_filename: str, dest_path: str, dest_filename: str) -> bool:
        return self._repo.is_transfer_history_exists(source_path, source_filename, dest_path, dest_filename)

    def insert(self, in_from, rmt_mode, in_path, out_path, dest, media_info) -> None:
        self._repo.insert_transfer_history(in_from, rmt_mode, in_path, out_path, dest, media_info)

    def get_page(self, search: Optional[str], page: int, rownum: int) -> Tuple[int, List[TransferHistoryEntity]]:
        count, rows = self._repo.get_transfer_history(search, page, rownum)
        if not rows:
            return count, []
        return count, [e for e in [TransferHistoryEntity.from_orm(r) for r in rows] if e is not None]

    def get_by_id(self, logid: int) -> Optional[TransferHistoryEntity]:
        row = self._repo.get_transfer_info_by_id(logid)
        return TransferHistoryEntity.from_orm(row)

    def get_by_tmdb(self, tmdbid: int, season: Optional[str] = None, season_episode: Optional[str] = None) -> List[TransferHistoryEntity]:
        rows = self._repo.get_transfer_info_by(tmdbid, season, season_episode)
        if not rows:
            return []
        return [e for e in [TransferHistoryEntity.from_orm(r) for r in rows] if e is not None]

    def delete(self, logid: int) -> None:
        self._repo.delete_transfer_history(logid)

    def delete_by_source(self, source_path: str, source_filename: str) -> None:
        self._repo.delete_transfer_history_by_source(source_path, source_filename)


class TransferUnknownRepositoryAdapter:
    def __init__(self, repo: Optional[TransferRepository] = None):
        self._repo = repo or TransferRepository()

    def insert(self, path: str, dest: str, mode: str) -> None:
        self._repo.insert_transfer_unknown(path, dest, mode)

    def get_all(self) -> List[TransferUnknownEntity]:
        rows = self._repo.get_transfer_unknowns()
        if not rows:
            return []
        return [e for e in [TransferUnknownEntity.from_orm(r) for r in rows] if e is not None]

    def get_by_id(self, tid: int) -> Optional[TransferUnknownEntity]:
        row = self._repo.get_transfer_unknown_by_id(tid)
        return TransferUnknownEntity.from_orm(row)

    def is_exists(self, path: str) -> bool:
        return self._repo.is_exists_transfer_unknowns(path)

    def delete(self, tid: int) -> None:
        self._repo.delete_transfer_unknown(tid)

    def truncate(self) -> None:
        self._repo.truncate_transfer_unknowns()


class TransferBlacklistRepositoryAdapter:
    def __init__(self, repo: Optional[TransferRepository] = None):
        self._repo = repo or TransferRepository()

    def is_exists(self, path: str) -> bool:
        return self._repo.is_exists_transfer_blacklist(path)

    def insert(self, path: str) -> None:
        self._repo.insert_transfer_blacklist(path)

    def delete(self, path: str) -> None:
        self._repo.delete_transfer_blacklist(path)

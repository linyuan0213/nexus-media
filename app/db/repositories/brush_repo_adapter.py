# -*- coding: utf-8 -*-
"""
刷流领域 Repository 适配器
"""
from typing import List, Optional

from app.domain.entities.brush import BrushTaskEntity, BrushTorrentEntity
from app.db.repositories.brush_repository import BrushRepository


class BrushTaskRepositoryAdapter:
    def __init__(self, repo: Optional[BrushRepository] = None):
        self._repo = repo or BrushRepository()

    def upsert(self, brush_id: Optional[int], item: dict) -> None:
        self._repo.update_brushtask(brush_id, item)

    def delete(self, brush_id: int) -> None:
        self._repo.delete_brushtask(brush_id)

    def get_all(self) -> List[BrushTaskEntity]:
        rows = self._repo.get_brushtasks()
        if not rows:
            return []
        return [e for e in [BrushTaskEntity.from_orm(r) for r in rows] if e is not None]

    def get_by_id(self, brush_id: int) -> Optional[BrushTaskEntity]:
        row = self._repo.get_brushtasks(brush_id=brush_id)
        return BrushTaskEntity.from_orm(row)

    def update_state(self, state: str, tid: Optional[int] = None) -> None:
        self._repo.update_brushtask_state(state, tid)

    def add_download_count(self, brush_id: int) -> None:
        self._repo.add_brushtask_download_count(brush_id)

    def get_total_size(self, brush_id: int) -> int:
        return self._repo.get_brushtask_totalsize(brush_id)


class BrushTorrentRepositoryAdapter:
    def __init__(self, repo: Optional[BrushRepository] = None):
        self._repo = repo or BrushRepository()

    def insert(self, task_id: str, torrent_name: str, enclosure: str, torrent_size: str,
               downloader: str, download_id: str) -> None:
        self._repo.add_brushtask_torrents(task_id, torrent_name, enclosure, torrent_size,
                                          downloader, download_id)

    def get_by_task(self, task_id: str) -> List[BrushTorrentEntity]:
        rows = self._repo.get_brushtask_torrents(task_id)
        if not rows:
            return []
        return [e for e in [BrushTorrentEntity.from_orm(r) for r in rows] if e is not None]

    def delete_by_task(self, task_id: str) -> None:
        self._repo.delete_brushtask_torrents(task_id)

    def delete_by_download_id(self, task_id: str, download_id: str) -> None:
        self._repo.delete_brushtask_torrent(task_id, download_id)

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

    # 兼容 BrushTaskRepository 方法名
    def get_brushtasks(self, brush_id=None):
        return self._repo.get_brushtasks(brush_id=brush_id)

    def get_brushtask_totalsize(self, task_id):
        return self._repo.get_brushtask_totalsize(task_id)

    def get_brushtask_torrents(self, brush_id, active=True):
        return self._repo.get_brushtask_torrents(brush_id, active)

    def update_brushtask(self, brushtask_id, item):
        return self._repo.update_brushtask(brushtask_id, item)

    def delete_brushtask(self, brushtask_id):
        return self._repo.delete_brushtask(brushtask_id)

    def update_brushtask_state(self, tid, state):
        return self._repo.update_brushtask_state(tid=tid, state=state)

    def get_brushtask_torrent_by_enclosure(self, enclosure):
        return self._repo.get_brushtask_torrent_by_enclosure(enclosure)

    def insert_brushtask_torrent(self, brush_id, title, enclosure, downloader, download_id, size):
        return self._repo.insert_brushtask_torrent(
            brush_id=brush_id, title=title, enclosure=enclosure,
            downloader=downloader, download_id=download_id, size=size
        )

    def delete_brushtask_torrent(self, taskid, download_id):
        return self._repo.delete_brushtask_torrent(taskid, download_id)

    def add_brushtask_upload_count(self, taskid, uploaded, downloaded, count):
        return self._repo.add_brushtask_upload_count(taskid, uploaded, downloaded, count)


class BrushTorrentRepositoryAdapter:
    def __init__(self, repo: Optional[BrushRepository] = None):
        self._repo = repo or BrushRepository()

    def insert(self, task_id: str, torrent_name: str, enclosure: str, torrent_size: str,
               downloader: str, download_id: str) -> None:
        self._repo.insert_brushtask_torrent(task_id, torrent_name, enclosure, downloader, download_id, torrent_size)

    def get_by_task(self, task_id: str) -> List[BrushTorrentEntity]:
        rows = self._repo.get_brushtask_torrents(task_id)
        if not rows:
            return []
        return [e for e in [BrushTorrentEntity.from_orm(r) for r in rows] if e is not None]

    def delete_by_task(self, task_id: str) -> None:
        self._repo.delete_brushtask_torrent(task_id, None)

    def delete_by_download_id(self, task_id: str, download_id: str) -> None:
        self._repo.delete_brushtask_torrent(task_id, download_id)

    # 兼容 BrushTaskRepository 方法名
    def get_brushtask_torrents(self, brush_id, active=True):
        return self._repo.get_brushtask_torrents(brush_id, active)

    def insert_brushtask_torrent(self, brush_id, title, enclosure, downloader, download_id, size):
        return self._repo.insert_brushtask_torrent(
            brush_id=brush_id, title=title, enclosure=enclosure,
            downloader=downloader, download_id=download_id, size=size
        )

    def update_brushtask_torrent_state(self, update_torrents):
        return self._repo.update_brushtask_torrent_state(update_torrents)

    def delete_brushtask_torrent(self, taskid, download_id):
        return self._repo.delete_brushtask_torrent(taskid, download_id)

    def add_brushtask_upload_count(self, taskid, uploaded, downloaded, count):
        return self._repo.add_brushtask_upload_count(taskid, uploaded, downloaded, count)

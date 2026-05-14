"""
刷流领域 Repository 适配器
"""

from app.db.models import SITEBRUSHTASK, SITEBRUSHTORRENTS
from app.db.repositories.brush_repository import BrushRepository
from app.domain.entities.brush import BrushTaskEntity, BrushTorrentEntity


class BrushTaskRepositoryAdapter:
    ...

    def delete_brushtask_torrent(self, taskid: int, download_id: str) -> None:
        return self._repo.delete_brushtask_torrent(taskid, download_id)

    def add_brushtask_upload_count(self, taskid: int, uploaded: int, downloaded: int, count: int) -> None:
        return self._repo.add_brushtask_upload_count(taskid, uploaded, downloaded, count)


class BrushTorrentRepositoryAdapter:
    def __init__(self, repo: BrushRepository | None = None):
        self._repo = repo or BrushRepository()

    def insert(
        self, task_id: str, torrent_name: str, enclosure: str, torrent_size: str, downloader: str, download_id: str
    ) -> None:
        self._repo.insert_brushtask_torrent(task_id, torrent_name, enclosure, downloader, download_id, torrent_size)

    def get_by_task(self, task_id: str) -> list[BrushTorrentEntity]:
        rows = self._repo.get_brushtask_torrents(task_id)
        if not rows:
            return []
        return [e for e in [BrushTorrentEntity.from_orm(r) for r in rows] if e is not None]

    def delete_by_task(self, task_id: str) -> None:
        self._repo.delete_brushtask_torrent(task_id, None)

    def delete_by_download_id(self, task_id: str, download_id: str) -> None:
        self._repo.delete_brushtask_torrent(task_id, download_id)

    # 兼容 BrushTaskRepository 方法名
    def get_brushtask_torrents(self, brush_id: int, active: bool = True) -> list[SITEBRUSHTORRENTS]:
        return self._repo.get_brushtask_torrents(brush_id, active)

    def insert_brushtask_torrent(self, brush_id: int, title: str, enclosure: str, downloader: str, download_id: str, size: str) -> None:
        return self._repo.insert_brushtask_torrent(
            brush_id=brush_id,
            title=title,
            enclosure=enclosure,
            downloader=downloader,
            download_id=download_id,
            size=size,
        )

    def update_brushtask_torrent_state(self, update_torrents: list) -> None:

    def delete_brushtask_torrent(self, taskid: int, download_id: str) -> None:

    def add_brushtask_upload_count(self, taskid: int, uploaded: int, downloaded: int, count: int) -> None:
        return self._repo.add_brushtask_upload_count(taskid, uploaded, downloaded, count)

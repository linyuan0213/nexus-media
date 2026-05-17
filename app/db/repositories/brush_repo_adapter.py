"""
刷流领域 Repository 适配器
"""

from app.db.models import SITEBRUSHTORRENTS
from app.db.repositories.brush_repository import BrushRepository
from app.domain.entities.brush import BrushRuleEntity, BrushTorrentEntity


class BrushRuleRepositoryAdapter:
    """刷流规则模板仓库适配器"""

    def __init__(self, repo: BrushRepository | None = None):
        self._repo = repo or BrushRepository()

    def insert(self, name: str, rss_rule: str, remove_rule: str, stop_rule: str) -> int:
        return self._repo.insert_brushrule(name, rss_rule, remove_rule, stop_rule)

    def update(self, rule_id: int, name: str | None = None, rss_rule: str | None = None, remove_rule: str | None = None, stop_rule: str | None = None) -> None:
        self._repo.update_brushrule(rule_id, name, rss_rule, remove_rule, stop_rule)

    def get_all(self) -> list[BrushRuleEntity]:
        rows = self._repo.get_brushrules()
        if not rows:
            return []
        if not isinstance(rows, list):
            rows = [rows]
        return [e for e in [BrushRuleEntity.from_orm(r) for r in rows] if e is not None]

    def get_by_id(self, rule_id: int) -> BrushRuleEntity | None:
        row = self._repo.get_brushrules(rule_id)
        if row is None:
            return None
        return BrushRuleEntity.from_orm(row)

    def delete(self, rule_id: int) -> None:
        self._repo.delete_brushrule(rule_id)


class BrushTaskRepositoryAdapter:
    def __init__(self, repo: BrushRepository | None = None):
        self._repo = repo or BrushRepository()

    def get_brushtasks(self, brush_id: int | None = None) -> list:
        return self._repo.get_brushtasks(brush_id)

    def get_brushtask_totalsize(self, task_id: int) -> int:
        return self._repo.get_brushtask_totalsize(task_id)

    def update_brushtask(self, brushtask_id: int, item: dict) -> None:
        self._repo.update_brushtask(brushtask_id, item)

    def delete_brushtask(self, brushtask_id: int) -> None:
        self._repo.delete_brushtask(brushtask_id)

    def update_brushtask_state(self, state: str, tid: int | None = None) -> None:
        self._repo.update_brushtask_state(state, tid)

    def add_brushtask_download_count(self, brush_id: int) -> None:
        self._repo.add_brushtask_download_count(brush_id)

    def get_brushtask_torrents(self, brush_id: int, active: bool = True) -> list:
        return self._repo.get_brushtask_torrents(brush_id, active)

    def get_brushtask_torrent_by_enclosure(self, enclosure: str) -> list:
        return self._repo.get_brushtask_torrent_by_enclosure(enclosure)

    def insert_brushtask_torrent(self, brush_id: int, title: str, enclosure: str, downloader: str, download_id: str, size: str) -> None:
        self._repo.insert_brushtask_torrent(brush_id=brush_id, title=title, enclosure=enclosure, downloader=downloader, download_id=download_id, size=size)

    def update_brushtask_torrent_state(self, update_torrents: list) -> None:
        self._repo.update_brushtask_torrent_state(update_torrents)

    def delete_brushtask_torrent(self, taskid: int, download_id: str) -> None:
        self._repo.delete_brushtask_torrent(taskid, download_id)

    def add_brushtask_upload_count(self, taskid: int, uploaded: int, downloaded: int, count: int) -> None:
        self._repo.add_brushtask_upload_count(taskid, uploaded, downloaded, count)


class BrushTorrentRepositoryAdapter:
    def __init__(self, repo: BrushRepository | None = None):
        self._repo = repo or BrushRepository()

    def insert(
        self, task_id: str, torrent_name: str, enclosure: str, torrent_size: str, downloader: str, download_id: str
    ) -> None:
        self._repo.insert_brushtask_torrent(int(task_id), torrent_name, enclosure, downloader, download_id, torrent_size)

    def get_by_task(self, task_id: str) -> list[BrushTorrentEntity]:
        rows = self._repo.get_brushtask_torrents(int(task_id))
        if not rows:
            return []
        return [e for e in [BrushTorrentEntity.from_orm(r) for r in rows] if e is not None]

    def delete_by_task(self, task_id: str) -> None:
        self._repo.delete_brushtask_torrent(int(task_id), None)

    def delete_by_download_id(self, task_id: str, download_id: str) -> None:
        self._repo.delete_brushtask_torrent(int(task_id), download_id)

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
        return self._repo.update_brushtask_torrent_state(update_torrents)

    def delete_brushtask_torrent(self, taskid: int, download_id: str) -> None:
        return self._repo.delete_brushtask_torrent(taskid, download_id)

    def add_brushtask_upload_count(self, taskid: int, uploaded: int, downloaded: int, count: int) -> None:
        return self._repo.add_brushtask_upload_count(taskid, uploaded, downloaded, count)

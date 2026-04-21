# -*- coding: utf-8 -*-
"""
下载领域 Repository 适配器
将旧版 DownloadRepository 适配为新领域接口
"""
from typing import List, Optional

from app.domain.entities.download import (
    DownloadHistoryEntity,
    DownloadSettingEntity,
    IndexerStatisticsEntity,
)
from app.db.repositories.download_repository import DownloadRepository


class DownloadHistoryRepositoryAdapter:
    """下载历史仓储适配器"""

    def __init__(self, repo: Optional[DownloadRepository] = None):
        self._repo = repo or DownloadRepository()

    def is_exists(self, enclosure: str, downloader: str, download_id: str) -> bool:
        return self._repo.is_exists_download_history(enclosure, downloader, download_id)

    def is_exists_by_tmdb(self, tmdb_id: str, season_episode: str) -> bool:
        return self._repo.is_exists_download_history_by_tmdb(tmdb_id, season_episode)

    def insert(self, media_info, downloader: str, download_id: str, save_dir: str) -> None:
        self._repo.insert_download_history(media_info, downloader, download_id, save_dir)

    def get_all(self, date: Optional[str] = None, hid: Optional[int] = None, num: int = 30, page: int = 1) -> List[DownloadHistoryEntity]:
        rows = self._repo.get_download_history(date=date, hid=hid, num=num, page=page)
        if not rows:
            return []
        return [entity for entity in [DownloadHistoryEntity.from_orm(r) for r in rows] if entity is not None]

    def get_by_title(self, title: str) -> List[DownloadHistoryEntity]:
        rows = self._repo.get_download_history_by_title(title)
        if not rows:
            return []
        return [entity for entity in [DownloadHistoryEntity.from_orm(r) for r in rows] if entity is not None]

    def get_by_path(self, path: str) -> Optional[DownloadHistoryEntity]:
        row = self._repo.get_download_history_by_path(path)
        if not row:
            return None
        return DownloadHistoryEntity.from_orm(row)

    def get_by_downloader(self, downloader: str, download_id: str) -> Optional[DownloadHistoryEntity]:
        row = self._repo.get_download_history_by_downloader(downloader, download_id)
        if not row:
            return None
        return DownloadHistoryEntity.from_orm(row)


class DownloadSettingRepositoryAdapter:
    """下载设置仓储适配器"""

    def __init__(self, repo: Optional[DownloadRepository] = None):
        self._repo = repo or DownloadRepository()

    def delete(self, sid: int) -> None:
        self._repo.delete_download_setting(sid)

    def get_all(self, sid: Optional[int] = None) -> List[DownloadSettingEntity]:
        rows = self._repo.get_download_setting(sid=sid)
        if not rows:
            return []
        return [entity for entity in [DownloadSettingEntity.from_orm(r) for r in rows] if entity is not None]

    def update(self,
               sid: int,
               name: str,
               category: str,
               tags: str,
               is_paused: bool,
               upload_limit: float,
               download_limit: float,
               ratio_limit: float,
               seeding_time_limit: float,
               downloader: str) -> None:
        self._repo.update_download_setting(
            sid=sid,
            name=name,
            category=category,
            tags=tags,
            is_paused=is_paused,
            upload_limit=upload_limit,
            download_limit=download_limit,
            ratio_limit=ratio_limit,
            seeding_time_limit=seeding_time_limit,
            downloader=downloader
        )


class IndexerStatisticsRepositoryAdapter:
    """索引器统计仓储适配器"""

    def __init__(self, repo: Optional[DownloadRepository] = None):
        self._repo = repo or DownloadRepository()

    def insert(self, indexer: str, itype: str, seconds: float, result: str) -> None:
        self._repo.insert_indexer_statistics(indexer, itype, seconds, result)

    def delete_all(self) -> None:
        self._repo.delete_all_indexer_statistics()

    def get_by_client(self, client_id: str) -> List[IndexerStatisticsEntity]:
        rows = self._repo.get_indexer_statistics(client_id)
        if not rows:
            return []
        result = []
        for r in rows:
            result.append(IndexerStatisticsEntity(
                indexer=r[0],
                total=r[1],
                fail=r[2],
                success=r[3],
                avg_seconds=r[4] or 0
            ))
        return result

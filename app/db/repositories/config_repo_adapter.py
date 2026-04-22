# -*- coding: utf-8 -*-
"""
配置领域 Repository 适配器
将旧版 ConfigRepository 适配为新领域接口
"""
from typing import List, Optional

from app.domain.entities.config import (
    MessageClientEntity,
    DownloaderEntity,
    FilterGroupEntity,
    FilterRuleEntity,
    MediaServerEntity,
    TorrentRemoveTaskEntity,
)
from app.domain.interfaces.config_repo import (
    IMessageClientRepository,
    IDownloaderRepository,
    IFilterGroupRepository,
    IFilterRuleRepository,
    IMediaServerRepository,
    ITorrentRemoveTaskRepository,
)
from app.db.repositories.config_repository import ConfigRepository


class MessageClientRepositoryAdapter(IMessageClientRepository):
    """消息客户端仓储适配器"""

    def __init__(self, repo: Optional[ConfigRepository] = None):
        self._repo = repo or ConfigRepository()

    def get_all(self) -> List[MessageClientEntity]:
        rows = self._repo.get_message_client()
        if not rows:
            return []
        return [entity for entity in [MessageClientEntity.from_orm(r) for r in rows] if entity is not None]

    def get_by_id(self, cid: int) -> Optional[MessageClientEntity]:
        rows = self._repo.get_message_client(cid)
        if not rows:
            return None
        return MessageClientEntity.from_orm(rows[0])

    def insert(self, name: str, ctype: str, config: str, switchs: list,
               interactive: int, enabled: int, note: str = '', templates=None) -> None:
        self._repo.insert_message_client(name, ctype, config, switchs, interactive, enabled, note, templates)

    def delete(self, cid: int) -> None:
        self._repo.delete_message_client(cid)


class DownloaderRepositoryAdapter(IDownloaderRepository):
    """下载器仓储适配器"""

    def __init__(self, repo: Optional[ConfigRepository] = None):
        self._repo = repo or ConfigRepository()

    def get_all(self) -> List[DownloaderEntity]:
        rows = self._repo.get_downloader()
        if not rows:
            return []
        return [entity for entity in [DownloaderEntity.from_orm(r) for r in rows] if entity is not None]

    def get_by_id(self, did: int) -> Optional[DownloaderEntity]:
        rows = self._repo.get_downloader(did)
        if not rows:
            return None
        return DownloaderEntity.from_orm(rows[0])

    def insert(self, name: str, dtype: str, config: str, transfer: str,
               only_nastool: int, match_path: int, enabled: int) -> None:
        self._repo.insert_downloader(name, dtype, config, transfer, only_nastool, match_path, enabled)

    def update(self, did: int, name: str, dtype: str, config: str, transfer: str,
               only_nastool: int, match_path: int, enabled: int) -> None:
        self._repo.update_downloader(did, name, dtype, config, transfer, only_nastool, match_path, enabled)

    def delete(self, did: int) -> None:
        self._repo.delete_downloader(did)


class FilterGroupRepositoryAdapter(IFilterGroupRepository):
    """过滤规则组仓储适配器"""

    def __init__(self, repo: Optional[ConfigRepository] = None):
        self._repo = repo or ConfigRepository()

    def get_all(self) -> List[FilterGroupEntity]:
        rows = self._repo.get_filter_group()
        if not rows:
            return []
        return [entity for entity in [FilterGroupEntity.from_orm(r) for r in rows] if entity is not None]

    def get_by_id(self, gid: int) -> Optional[FilterGroupEntity]:
        rows = self._repo.get_filter_group(gid)
        if not rows:
            return None
        return FilterGroupEntity.from_orm(rows[0])

    def insert(self, name: str, default: int = 0) -> int:
        return self._repo.insert_filter_group(name, default)

    def delete(self, gid: int) -> None:
        self._repo.delete_filter_group(gid)


class FilterRuleRepositoryAdapter(IFilterRuleRepository):
    """过滤规则仓储适配器"""

    def __init__(self, repo: Optional[ConfigRepository] = None):
        self._repo = repo or ConfigRepository()

    def get_by_group(self, group_id: int) -> List[FilterRuleEntity]:
        rows = self._repo.get_filter_rule(group_id)
        if not rows:
            return []
        return [entity for entity in [FilterRuleEntity.from_orm(r) for r in rows] if entity is not None]

    def insert(self, group_id: int, name: str, include: str, exclude: str,
               note: str, priority: int = 0) -> None:
        self._repo.insert_filter_rule(group_id, name, include, exclude, note, priority)

    def delete_by_group(self, group_id: int) -> None:
        self._repo.delete_filter_rule(group_id)


class MediaServerRepositoryAdapter(IMediaServerRepository):
    """媒体服务器仓储适配器"""

    def __init__(self, repo: Optional[ConfigRepository] = None):
        self._repo = repo or ConfigRepository()

    def get_all(self) -> List[MediaServerEntity]:
        rows = self._repo.get_mediaserver()
        if not rows:
            return []
        return [entity for entity in [MediaServerEntity.from_orm(r) for r in rows] if entity is not None]

    def get_by_id(self, sid: int) -> Optional[MediaServerEntity]:
        rows = self._repo.get_mediaserver(sid)
        if not rows:
            return None
        return MediaServerEntity.from_orm(rows[0])

    def insert(self, name: str, ctype: str, config: str, enabled: int) -> None:
        self._repo.insert_mediaserver(name, ctype, config, enabled)

    def delete(self, sid: int) -> None:
        self._repo.delete_mediaserver(sid)


class TorrentRemoveTaskRepositoryAdapter(ITorrentRemoveTaskRepository):
    """自动删种任务仓储适配器"""

    def __init__(self, repo: Optional[ConfigRepository] = None):
        self._repo = repo or ConfigRepository()

    def get_all(self) -> List[TorrentRemoveTaskEntity]:
        rows = self._repo.get_torrent_remove_task()
        if not rows:
            return []
        return [entity for entity in [TorrentRemoveTaskEntity.from_orm(r) for r in rows] if entity is not None]

    def get_by_id(self, tid: int) -> Optional[TorrentRemoveTaskEntity]:
        rows = self._repo.get_torrent_remove_task(tid)
        if not rows:
            return None
        return TorrentRemoveTaskEntity.from_orm(rows[0])

    def insert(self, name: str, downloader: str, config: str, enabled: int = 1) -> None:
        self._repo.insert_torrent_remove_task(name, downloader, config, enabled)

    def delete(self, tid: int) -> None:
        self._repo.delete_torrent_remove_task(tid)

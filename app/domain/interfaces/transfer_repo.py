# -*- coding: utf-8 -*-
"""
转移领域 Repository 接口（Python Protocol）
"""
from typing import List, Optional, Protocol, Tuple

from app.domain.entities.transfer import (
    TransferBlacklistEntity,
    TransferHistoryEntity,
    TransferUnknownEntity,
)


class ITransferHistoryRepository(Protocol):
    """转移历史仓储接口"""

    def is_exists(self, source_path: str, source_filename: str, dest_path: str, dest_filename: str) -> bool:
        ...

    def insert(self, in_from, rmt_mode, in_path, out_path, dest, media_info) -> None:
        ...

    def get_page(self, search: Optional[str], page: int, rownum: int) -> Tuple[int, List[TransferHistoryEntity]]:
        ...

    def get_by_id(self, logid: int) -> Optional[TransferHistoryEntity]:
        ...

    def get_by_tmdb(self, tmdbid: int, season: Optional[str] = None, season_episode: Optional[str] = None) -> List[TransferHistoryEntity]:
        ...

    def delete(self, logid: int) -> None:
        ...

    def delete_by_source(self, source_path: str, source_filename: str) -> None:
        ...


class ITransferUnknownRepository(Protocol):
    """未知转移记录仓储接口"""

    def insert(self, path: str, dest: str, mode: str) -> None:
        ...

    def get_all(self) -> List[TransferUnknownEntity]:
        ...

    def get_by_id(self, tid: int) -> Optional[TransferUnknownEntity]:
        ...

    def is_exists(self, path: str) -> bool:
        ...

    def delete(self, tid: int) -> None:
        ...

    def truncate(self) -> None:
        ...


class ITransferBlacklistRepository(Protocol):
    """转移黑名单仓储接口"""

    def is_exists(self, path: str) -> bool:
        ...

    def insert(self, path: str) -> None:
        ...

    def delete(self, path: str) -> None:
        ...

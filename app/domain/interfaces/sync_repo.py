# -*- coding: utf-8 -*-
"""
同步领域 Repository 接口（Python Protocol）
定义 Sync（目录同步配置）的仓储契约
"""
from typing import List, Optional, Protocol

from app.domain.entities.sync import SyncPathEntity


class ISyncPathRepository(Protocol):
    """目录同步路径仓储接口"""

    def get_all(self, sid: Optional[int] = None) -> List[SyncPathEntity]:
        """查询所有同步路径配置，或根据ID查询单个"""
        ...

    def insert(self, source: str, dest: str, unknown: str, mode: str,
               compatibility: int, rename: int, enabled: int, note: Optional[str] = None) -> None:
        """插入同步路径配置"""
        ...

    def delete(self, sid: int) -> None:
        """删除同步路径配置"""
        ...

    def update_state(self, sid: Optional[int] = None, compatibility: Optional[int] = None,
                     rename: Optional[int] = None, enabled: Optional[int] = None) -> None:
        """更新同步路径状态"""
        ...

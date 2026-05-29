"""
同步领域 Repository 接口（Python Protocol）
定义 Sync（目录同步配置）的仓储契约
"""

from typing import Protocol

from app.domain.entities.sync import SyncPathEntity


class ISyncPathRepository(Protocol):
    """目录同步路径仓储接口"""

    def get_all(self, sid: int | None = None) -> list[SyncPathEntity]:
        """查询所有同步路径配置，或根据ID查询单个"""
        ...

    def insert(
        self,
        source: str,
        dest: str,
        unknown: str,
        mode: str,
        compatibility: int,
        rename: int,
        enabled: int,
        note: str | None = None,
    ) -> None:
        """插入同步路径配置"""
        ...

    def delete(self, sid: int) -> None:
        """删除同步路径配置"""
        ...

    def update_state(
        self,
        sid: int | None = None,
        compatibility: int | None = None,
        rename: int | None = None,
        enabled: int | None = None,
    ) -> None:
        """更新同步路径状态"""
        ...

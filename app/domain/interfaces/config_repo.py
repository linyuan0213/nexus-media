"""
配置领域 Repository 接口（Python Protocol）
定义 Config（消息客户端、下载器、过滤规则等）的仓储契约
"""
from typing import Protocol

from app.domain.entities.config import (
    DownloaderEntity,
    FilterGroupEntity,
    FilterRuleEntity,
    MediaServerEntity,
    MessageClientEntity,
    TorrentRemoveTaskEntity,
)


class IMessageClientRepository(Protocol):
    """消息客户端仓储接口"""

    def get_all(self) -> list[MessageClientEntity]:
        """获取所有消息客户端"""
        ...

    def get_by_id(self, cid: int) -> MessageClientEntity | None:
        """根据ID获取消息客户端"""
        ...

    def insert(self, name: str, ctype: str, config: str, switchs: list,
               interactive: int, enabled: int, note: str = '', templates=None) -> None:
        """插入消息客户端"""
        ...

    def delete(self, cid: int) -> None:
        """删除消息客户端"""
        ...


class IDownloaderRepository(Protocol):
    """下载器仓储接口"""

    def get_all(self) -> list[DownloaderEntity]:
        """获取所有下载器"""
        ...

    def get_by_id(self, did: int) -> DownloaderEntity | None:
        """根据ID获取下载器"""
        ...

    def insert(self, name: str, dtype: str, config: str, transfer: str,
               only_nastool: int, match_path: int, enabled: int) -> None:
        """插入下载器"""
        ...

    def update(self, did: int, name: str, dtype: str, config: str, transfer: str,
               only_nastool: int, match_path: int, enabled: int) -> None:
        """更新下载器"""
        ...

    def delete(self, did: int) -> None:
        """删除下载器"""
        ...


class IFilterGroupRepository(Protocol):
    """过滤规则组仓储接口"""

    def get_all(self) -> list[FilterGroupEntity]:
        """获取所有过滤规则组"""
        ...

    def get_by_id(self, gid: int) -> FilterGroupEntity | None:
        """根据ID获取过滤规则组"""
        ...

    def insert(self, name: str, default: int = 0) -> int:
        """插入过滤规则组，返回新组ID"""
        ...

    def delete(self, gid: int) -> None:
        """删除过滤规则组"""
        ...


class IFilterRuleRepository(Protocol):
    """过滤规则仓储接口"""

    def get_by_group(self, group_id: int) -> list[FilterRuleEntity]:
        """根据规则组ID获取规则列表"""
        ...

    def insert(self, group_id: int, name: str, include: str, exclude: str,
               note: str, priority: int = 0) -> None:
        """插入过滤规则"""
        ...

    def delete_by_group(self, group_id: int) -> None:
        """删除指定规则组的所有规则"""
        ...


class IMediaServerRepository(Protocol):
    """媒体服务器仓储接口"""

    def get_all(self) -> list[MediaServerEntity]:
        """获取所有媒体服务器"""
        ...

    def get_by_id(self, sid: int) -> MediaServerEntity | None:
        """根据ID获取媒体服务器"""
        ...

    def insert(self, name: str, ctype: str, config: str, enabled: int) -> None:
        """插入媒体服务器"""
        ...

    def delete(self, sid: int) -> None:
        """删除媒体服务器"""
        ...


class ITorrentRemoveTaskRepository(Protocol):
    """自动删种任务仓储接口"""

    def get_all(self) -> list[TorrentRemoveTaskEntity]:
        """获取所有删种任务"""
        ...

    def get_by_id(self, tid: int) -> TorrentRemoveTaskEntity | None:
        """根据ID获取删种任务"""
        ...

    def insert(self, name: str, downloader: str, config: str, enabled: int = 1) -> None:
        """插入删种任务"""
        ...

    def delete(self, tid: int) -> None:
        """删除删种任务"""
        ...

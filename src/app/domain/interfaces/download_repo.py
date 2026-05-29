"""
下载领域 Repository 接口（Python Protocol）
定义 DownloadHistory、DownloadSetting、IndexerStatistics 的仓储契约
"""

from typing import Protocol

from app.domain.entities.download import (
    DownloadHistoryEntity,
    DownloadSettingEntity,
    IndexerStatisticsEntity,
)


class IDownloadHistoryRepository(Protocol):
    """下载历史仓储接口"""

    def is_exists(self, enclosure: str, downloader: str, download_id: str) -> bool:
        """查询下载历史是否存在"""
        ...

    def is_exists_by_tmdb(self, tmdb_id: str, season_episode: str) -> bool:
        """根据TMDB ID和季集信息查询下载历史是否存在"""
        ...

    def insert(self, media_info, downloader: str, download_id: str, save_dir: str) -> None:
        """新增下载历史"""
        ...

    def get_all(
        self, date: str | None = None, hid: int | None = None, num: int = 30, page: int = 1
    ) -> list[DownloadHistoryEntity]:
        """查询下载历史列表"""
        ...

    def get_by_title(self, title: str) -> list[DownloadHistoryEntity]:
        """根据标题查找下载历史"""
        ...

    def get_by_path(self, path: str) -> DownloadHistoryEntity | None:
        """根据路径查找下载历史"""
        ...

    def get_download_history_by_path(self, path: str):
        """根据路径查找下载历史（兼容旧方法名）"""
        ...

    def get_by_downloader(self, downloader: str, download_id: str) -> DownloadHistoryEntity | None:
        """根据下载器查找下载历史"""
        ...


class IDownloadSettingRepository(Protocol):
    """下载设置仓储接口"""

    def delete(self, sid: int) -> None:
        """删除下载设置"""
        ...

    def get_all(self, sid: int | None = None) -> list[DownloadSettingEntity]:
        """查询下载设置列表"""
        ...

    def update(
        self,
        sid: int,
        name: str,
        category: str,
        tags: str,
        is_paused: bool,
        upload_limit: float,
        download_limit: float,
        ratio_limit: float,
        seeding_time_limit: float,
        downloader: str,
    ) -> None:
        """新增或更新下载设置"""
        ...


class IIndexerStatisticsRepository(Protocol):
    """索引器统计仓储接口"""

    def insert(self, indexer: str, itype: str, seconds: float, result: str) -> None:
        """插入索引器统计"""
        ...

    def delete_all(self) -> None:
        """删除所有统计"""
        ...

    def get_by_client(self, client_id: str) -> list[IndexerStatisticsEntity]:
        """查询索引器统计"""
        ...

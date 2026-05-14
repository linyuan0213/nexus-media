"""
下载领域实体
定义Downloader、DownloadHistory、DownloadSetting的领域模型
"""
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class DownloaderEntity:
    """下载器配置实体"""
    id: int
    name: str
    enabled: bool
    type: str
    transfer: bool
    only_nastool: bool
    match_path: bool
    rmt_mode: str
    config: str  # JSON配置字符串
    download_dir: str

    @classmethod
    def from_orm(cls, orm_model) -> Optional["DownloaderEntity"]:
        """从ORM模型创建领域实体"""
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            name=orm_model.NAME or "",
            enabled=bool(orm_model.ENABLED),
            type=orm_model.TYPE or "",
            transfer=bool(orm_model.TRANSFER),
            only_nastool=bool(orm_model.ONLY_NASTOOL),
            match_path=bool(orm_model.MATCH_PATH),
            rmt_mode=orm_model.RMT_MODE or "",
            config=orm_model.CONFIG or "{}",
            download_dir=orm_model.DOWNLOAD_DIR or ""
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "type": self.type,
            "transfer": self.transfer,
            "only_nastool": self.only_nastool,
            "match_path": self.match_path,
            "rmt_mode": self.rmt_mode,
            "config": self.config,
            "download_dir": self.download_dir
        }


@dataclass
class DownloadHistoryEntity:
    """下载历史实体"""
    id: int
    title: str
    year: str
    media_type: str  # TYPE字段
    tmdb_id: str
    season_episode: str  # SE字段
    vote: str
    poster: str
    overview: str
    torrent: str
    enclosure: str
    site: str
    description: str  # DESC字段
    downloader: str
    download_id: str
    save_path: str
    date: str

    @classmethod
    def from_orm(cls, orm_model) -> Optional["DownloadHistoryEntity"]:
        """从ORM模型创建领域实体"""
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            title=orm_model.TITLE or "",
            year=orm_model.YEAR or "",
            media_type=orm_model.TYPE or "",
            tmdb_id=orm_model.TMDBID or "",
            season_episode=orm_model.SE or "",
            vote=orm_model.VOTE or "",
            poster=orm_model.POSTER or "",
            overview=orm_model.OVERVIEW or "",
            torrent=orm_model.TORRENT or "",
            enclosure=orm_model.ENCLOSURE or "",
            site=orm_model.SITE or "",
            description=orm_model.DESC or "",
            downloader=orm_model.DOWNLOADER or "",
            download_id=orm_model.DOWNLOAD_ID or "",
            save_path=orm_model.SAVE_PATH or "",
            date=orm_model.DATE or ""
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "title": self.title,
            "year": self.year,
            "type": self.media_type,
            "tmdbid": self.tmdb_id,
            "se": self.season_episode,
            "vote": self.vote,
            "poster": self.poster,
            "overview": self.overview,
            "torrent": self.torrent,
            "enclosure": self.enclosure,
            "site": self.site,
            "desc": self.description,
            "downloader": self.downloader,
            "download_id": self.download_id,
            "save_path": self.save_path,
            "date": self.date
        }


@dataclass
class DownloadSettingEntity:
    """下载设置实体"""
    id: int
    name: str
    category: str
    tags: str
    is_paused: bool
    upload_limit: int  # KB/s
    download_limit: int  # KB/s
    ratio_limit: int  # 百分比(如200表示2.0)
    seeding_time_limit: int  # 分钟
    downloader: str
    note: str

    @classmethod
    def from_orm(cls, orm_model) -> Optional["DownloadSettingEntity"]:
        """从ORM模型创建领域实体"""
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            name=orm_model.NAME or "",
            category=orm_model.CATEGORY or "",
            tags=orm_model.TAGS or "",
            is_paused=bool(orm_model.IS_PAUSED),
            upload_limit=orm_model.UPLOAD_LIMIT or 0,
            download_limit=orm_model.DOWNLOAD_LIMIT or 0,
            ratio_limit=orm_model.RATIO_LIMIT or 0,
            seeding_time_limit=orm_model.SEEDING_TIME_LIMIT or 0,
            downloader=orm_model.DOWNLOADER or "",
            note=orm_model.NOTE or ""
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "tags": self.tags,
            "is_paused": self.is_paused,
            "upload_limit": self.upload_limit,
            "download_limit": self.download_limit,
            "ratio_limit": self.ratio_limit,
            "seeding_time_limit": self.seeding_time_limit,
            "downloader": self.downloader,
            "note": self.note
        }


@dataclass
class IndexerStatisticsEntity:
    """索引器统计实体"""
    indexer: str
    total: int
    fail: int
    success: int
    avg_seconds: float

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "indexer": self.indexer,
            "total": self.total,
            "fail": self.fail,
            "success": self.success,
            "avg_seconds": round(self.avg_seconds, 2) if self.avg_seconds else 0
        }

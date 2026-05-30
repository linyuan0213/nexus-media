"""
下载领域实体
定义Downloader、DownloadHistory、DownloadSetting的领域模型
"""

import re
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
    only_nexus_media: bool
    match_path: bool
    rmt_mode: str
    config: str  # JSON配置字符串
    download_dir: str

    @property
    def is_available(self) -> bool:
        """下载器是否可用"""
        return self.enabled and bool(self.type)

    @property
    def should_transfer(self) -> bool:
        """下载完成后是否需要自动转移"""
        return self.transfer

    @property
    def should_match_path(self) -> bool:
        """是否按路径匹配媒体库"""
        return self.match_path

    @property
    def is_nexus_media_only(self) -> bool:
        """是否只处理本系统添加的种子"""
        return self.only_nexus_media

    @property
    def parsed_config(self) -> dict[str, Any]:
        """解析JSON配置"""
        import json

        try:
            return json.loads(self.config) if self.config else {}
        except Exception:
            return {}

    @property
    def host(self) -> str | None:
        """获取下载器主机地址"""
        return self.parsed_config.get("host") or self.parsed_config.get("ip")

    @property
    def port(self) -> int | None:
        """获取下载器端口"""
        p = self.parsed_config.get("port")
        return int(p) if p else None

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
            only_nexus_media=bool(orm_model.ONLY_NEXUS_MEDIA),
            match_path=bool(orm_model.MATCH_PATH),
            rmt_mode=orm_model.RMT_MODE or "",
            config=orm_model.CONFIG or "{}",
            download_dir=orm_model.DOWNLOAD_DIR or "",
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "type": self.type,
            "transfer": self.transfer,
            "only_nexus_media": self.only_nexus_media,
            "match_path": self.match_path,
            "rmt_mode": self.rmt_mode,
            "config": self.config,
            "download_dir": self.download_dir,
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

    @property
    def is_movie(self) -> bool:
        return self.media_type == "电影"

    @property
    def is_tv(self) -> bool:
        return self.media_type == "电视剧"

    @property
    def is_anime(self) -> bool:
        return self.media_type == "动漫"

    @property
    def parsed_season(self) -> int | None:
        """从 season_episode 解析季号，如 S01 -> 1"""
        if not self.season_episode:
            return None
        m = re.search(r"S(\d+)", self.season_episode, re.IGNORECASE)
        return int(m.group(1)) if m else None

    @property
    def parsed_episodes(self) -> list[int]:
        """从 season_episode 解析集号列表，如 S01E01 -> [1], S01E01-E02 -> [1, 2]"""
        if not self.season_episode:
            return []
        matches = re.findall(r"E(\d+)", self.season_episode, re.IGNORECASE)
        return [int(m) for m in matches]

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
            date=orm_model.DATE or "",
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
            "date": self.date,
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

    @property
    def has_upload_limit(self) -> bool:
        return self.upload_limit > 0

    @property
    def has_download_limit(self) -> bool:
        return self.download_limit > 0

    @property
    def has_ratio_limit(self) -> bool:
        return self.ratio_limit > 0

    @property
    def has_seeding_time_limit(self) -> bool:
        return self.seeding_time_limit > 0

    @property
    def ratio_float(self) -> float:
        """分享率限制转换为浮点数"""
        return round(self.ratio_limit / 100, 2) if self.ratio_limit else 0.0

    @property
    def seeding_time_hours(self) -> float:
        """做种时间限制转换为小时"""
        return round(self.seeding_time_limit / 60, 1) if self.seeding_time_limit else 0.0

    @property
    def tag_list(self) -> list[str]:
        """标签列表"""
        return [t.strip() for t in self.tags.split(",") if t.strip()] if self.tags else []

    @property
    def is_default(self) -> bool:
        """是否为默认设置"""
        return not self.category and not self.tags

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
            note=orm_model.NOTE or "",
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
            "note": self.note,
        }


@dataclass
class IndexerStatisticsEntity:
    """索引器统计实体"""

    indexer: str
    total: int
    fail: int
    success: int
    avg_seconds: float

    @property
    def success_rate(self) -> float:
        """成功率百分比"""
        if self.total <= 0:
            return 0.0
        return round(self.success / self.total * 100, 1)

    @property
    def fail_rate(self) -> float:
        """失败率百分比"""
        if self.total <= 0:
            return 0.0
        return round(self.fail / self.total * 100, 1)

    @property
    def is_healthy(self) -> bool:
        """索引器是否健康（成功率≥80%）"""
        return self.success_rate >= 80.0

    @property
    def is_slow(self) -> bool:
        """索引器是否响应慢（平均响应>5秒）"""
        return self.avg_seconds > 5.0

    @property
    def is_unusable(self) -> bool:
        """索引器是否不可用（成功率<50%且请求>10次）"""
        return self.total >= 10 and self.success_rate < 50.0

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "indexer": self.indexer,
            "total": self.total,
            "fail": self.fail,
            "success": self.success,
            "avg_seconds": round(self.avg_seconds, 2) if self.avg_seconds else 0,
            "success_rate": self.success_rate,
        }

from dataclasses import dataclass, field
from enum import Enum

TorrentStatus = Enum(
    "TorrentStatus",
    ("Downloading", "Uploading", "Checking", "Queued", "Paused", "Stopped", "Pending", "Error", "Unknown"),
)


@dataclass
class Torrent:
    """种子信息 DTO"""

    id: str | None = None  # 种子id
    name: str | None = None  # 种子名称
    size: int = 0  # 种子大小
    downloaded: int = 0  # 下载量
    uploaded: int = 0  # 上传量
    ratio: float = 0  # 分享率
    add_time: str | None = None  # 种子添加时间
    seeding_time: int = 0  # 做种时间
    download_time: int = 0  # 下载时间
    avg_upload_speed: float = 0  # 平均上传速度
    iatime: int = 0  # 未活跃时间
    labels: list[str] = field(default_factory=list)  # 种子标签
    status: TorrentStatus | None = None  # 种子状态
    save_path: str | None = None  # 保存路径
    content_path: str | None = None  # 文件完整路径
    trackers: list[str] = field(default_factory=list)  # 种子tracker
    tracker_error: str = ""  # Tracker 错误信息（非空表示有错误）
    category: list[str] = field(default_factory=list)  # 种子分类
    progress: float = 0  # 种子进度
    download_speed: int = 0  # 下载速度
    upload_speed: int = 0  # 上传速度
    eta: int = 0  # eta


@dataclass
class DownloadResultDTO:
    """下载结果 DTO"""

    success: bool = False
    message: str = ""


@dataclass
class DownloadingTorrentDTO:
    """正在下载任务 DTO（含媒体信息组装后）"""

    id: str = ""
    name: str = ""
    title: str = ""
    image: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class IndexerStatisticsDTO:
    """索引器统计 DTO"""

    name: str = ""
    total: int = 0
    fail: int = 0
    success: int = 0
    avg: float = 0.0

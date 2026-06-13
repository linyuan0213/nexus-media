"""事件负载定义 — 类型化的事件数据结构."""

from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# 媒体相关
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MediaTransferFinishedPayload:
    """媒体转移完成事件负载"""

    in_path: str
    file: str
    target_path: str
    dest: str
    media_info: dict[str, Any]


@dataclass(frozen=True)
class MediaEpisodeTransferredPayload:
    """单集转移完成事件负载（驱动订阅进度更新）"""

    tmdb_id: str
    title: str
    season: str
    episodes: list[int]
    total_episodes: int


@dataclass(frozen=True)
class MediaSourceDeletedPayload:
    """媒体源文件删除事件负载"""

    media_info: dict[str, Any]
    path: str
    filename: str


@dataclass(frozen=True)
class LibraryFileDeletedPayload:
    """媒体库文件删除事件负载"""

    media_info: dict[str, Any]
    path: str
    filename: str


# ---------------------------------------------------------------------------
# 下载相关
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DownloadStartedPayload:
    """下载开始事件负载"""

    media_info: dict[str, Any]
    is_paused: bool
    tag: str | None
    download_dir: str | None
    download_setting: int | None
    downloader_id: str | None
    torrent_file: str | None


@dataclass(frozen=True)
class DownloadFailedPayload:
    """下载失败事件负载"""

    media_info: dict[str, Any]
    reason: str


@dataclass(frozen=True)
class DownloadCompletedPayload:
    """下载完成事件负载"""

    downloader_id: str
    task_id: str
    path: str
    tags: list[str] | None = None
    name: str | None = None


# ---------------------------------------------------------------------------
# 订阅相关
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SubscribeFinishedPayload:
    """订阅完成事件负载"""

    media_info: dict[str, Any]
    rssid: int


@dataclass(frozen=True)
class SubscribeAddPayload:
    """订阅添加事件负载"""

    media: dict[str, Any]
    rssid: int | str
    rss_sites: list[str] | None = None
    search_sites: list[str] | None = None
    over_edition: bool = False
    filter_restype: str | None = None
    filter_pix: str | None = None
    filter_team: str | None = None
    filter_rule: int | None = None
    save_path: str | None = None
    download_setting: int | None = None
    total_ep: int | None = None
    current_ep: int | None = None
    fuzzy_match: bool = False
    keyword: str | None = None


@dataclass(frozen=True)
class RssAutoSubscribeRequestedPayload:
    """RSS自动化订阅请求事件负载"""

    mtype: Any
    name: str
    year: str
    channel: str
    season: str | None = None
    rss_sites: list[str] | None = None
    search_sites: list[str] | None = None
    over_edition: bool = False
    filter_restype: str | None = None
    filter_pix: str | None = None
    filter_team: str | None = None
    filter_rule: int | None = None
    save_path: str | None = None
    download_setting: int | None = None


# ---------------------------------------------------------------------------
# 搜索相关
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SearchStartPayload:
    """搜索开始事件负载"""

    key_word: str
    media_info: dict[str, Any] | None
    filter_args: dict[str, Any] | None
    search_type: str | None


# ---------------------------------------------------------------------------
# 字幕相关
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SubtitleDownloadPayload:
    """字幕下载事件负载"""

    media_info: dict[str, Any]
    file: str
    file_ext: str
    bluray: bool = False


# ---------------------------------------------------------------------------
# 转移失败
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TransferFailPayload:
    """转移失败事件负载"""

    path: str
    count: int
    reason: str


# ---------------------------------------------------------------------------
# 消息相关
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MessageIncomingPayload:
    """消息 incoming 事件负载"""

    channel: str
    user_id: str | None
    user_name: str | None
    message: str

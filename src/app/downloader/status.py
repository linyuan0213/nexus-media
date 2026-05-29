from app.schemas.download import TorrentStatus

# 通用状态中文映射
TORRENT_STATUS_LABELS = {
    TorrentStatus.Downloading: "正在下载",
    TorrentStatus.Uploading: "正在上传",
    TorrentStatus.Checking: "检查中",
    TorrentStatus.Queued: "排队",
    TorrentStatus.Paused: "暂停",
    TorrentStatus.Stopped: "暂停",
    TorrentStatus.Pending: "等待",
    TorrentStatus.Error: "错误",
    TorrentStatus.Unknown: "未知状态",
}


def status_label(status: TorrentStatus) -> str:
    return TORRENT_STATUS_LABELS.get(status, "未知状态")

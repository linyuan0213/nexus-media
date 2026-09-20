"""刷流免费恢复启动需受活跃星期/时段约束."""

from unittest.mock import MagicMock

from app.schemas.download import TorrentStatus
from app.services.brush.torrent_lifecycle import BrushTorrentLifecycle


def _lifecycle(in_window: bool):
    helper = MagicMock()
    helper.is_in_time_range.return_value = in_window
    helper.is_in_active_weekdays.return_value = in_window
    helper.get_torrent_attr.return_value = ("https://x", {"free": True})
    downloader = MagicMock()
    torrent = MagicMock()
    torrent.id = "h1"
    torrent.status = TorrentStatus.Paused
    torrent.name = "t"
    downloader.get_torrents.return_value = [torrent]
    lc = BrushTorrentLifecycle(helper, MagicMock(), downloader, MagicMock(), MagicMock())
    return lc, downloader, torrent


def _run(lc, taskinfo):
    lc._resume_free_torrents(
        1,
        taskinfo,
        "任务",
        1,
        {"h1": "https://x/enclosure"},
        "qb",
        False,
        {"name": "站"},
        {"h1": "https://x/details"},
    )


def test_resume_skipped_outside_active_window():
    lc, downloader, _ = _lifecycle(in_window=False)
    _run(lc, {"time_range": "05:00-06:00", "active_weekdays": "6"})
    downloader.start_torrents.assert_not_called()


def test_resume_allowed_inside_active_window():
    lc, downloader, _ = _lifecycle(in_window=True)
    _run(lc, {"time_range": "05:00-06:00", "active_weekdays": "6"})
    downloader.start_torrents.assert_called_once()

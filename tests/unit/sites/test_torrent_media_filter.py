"""种子内容过滤：纯广告 .url 种子不得创建下载任务."""

from app.sites.download.torrent import Torrent


def test_torrent_with_only_url_is_rejected():
    info = b"d4:name18:2026 test site.url12:piece lengthi1e6:pieces0:e"
    torrent = b"d4:info" + info + b"e"
    assert Torrent.torrent_has_media(torrent) is False


def test_torrent_with_video_is_allowed():
    info = b"d4:name9:movie.mp412:piece lengthi1e6:pieces0:e"
    torrent = b"d4:info" + info + b"e"
    assert Torrent.torrent_has_media(torrent) is True

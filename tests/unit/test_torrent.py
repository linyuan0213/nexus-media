"""Tests for app.sites.torrent."""

from app.domain.mediatypes import MediaType
from app.media.models import MediaInfo
from app.sites.torrent import Torrent


class _MediaInfo(MediaInfo):
    def __init__(self, **kwargs):
        super().__init__()
        for k, v in kwargs.items():
            setattr(self, k, v)


class TestTorrentGetDownloadList:
    """Test suite for Torrent.get_download_list."""

    def test_prioritizes_season_pack_over_single_episodes(self):
        single = _MediaInfo(
            title="Single Ep",
            type=MediaType.ANIME,
            tmdb_id=1,
            begin_season=1,
            begin_episode=1,
            end_episode=1,
            res_order=1,
            site_order=1,
            seeders=100,
        )
        pack = _MediaInfo(
            title="Season Pack",
            type=MediaType.ANIME,
            tmdb_id=1,
            begin_season=1,
            res_order=1,
            site_order=1,
            seeders=10,
        )
        result = Torrent.get_download_list([single, pack], download_order="default")
        assert result[0].title == "Season Pack"

    def test_prioritizes_multi_episode_pack(self):
        single = _MediaInfo(
            title="Single Ep",
            type=MediaType.ANIME,
            tmdb_id=1,
            begin_season=1,
            begin_episode=1,
            end_episode=1,
            res_order=1,
            site_order=1,
            seeders=100,
        )
        multi = _MediaInfo(
            title="E01-E12 Pack",
            type=MediaType.ANIME,
            tmdb_id=1,
            begin_season=1,
            begin_episode=1,
            end_episode=12,
            res_order=1,
            site_order=1,
            seeders=50,
        )
        result = Torrent.get_download_list([single, multi], download_order="default")
        assert result[0].title == "E01-E12 Pack"

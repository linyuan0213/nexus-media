"""DownloadCore 媒体库存在性检查回归测试."""

from unittest.mock import MagicMock

import pytest

from app.domain.media_types import ProviderMediaType
from app.services.download_core import DownloadCore
from app.sites.download.torrent import Torrent


@pytest.mark.parametrize("total_ep", [{1: 10}, {"1": 10}])
@pytest.mark.parametrize("season", [1, "1"])
def test_check_exists_medias_accepts_numeric_or_string_season_keys(total_ep, season):
    core = DownloadCore.__new__(DownloadCore)
    core._filetransfer = MagicMock()
    core._filetransfer.get_no_exists_medias.return_value = []
    media = MagicMock()
    media.type = ProviderMediaType.SERIES
    media.total_episodes = 0
    media.get_season_seq.return_value = season

    exists, missing, _ = core.check_exists_medias(media, total_ep=total_ep)

    assert exists is True
    assert missing == {}
    core._filetransfer.get_no_exists_medias.assert_called_once_with(media, season=season, total_num=10)


def test_check_exists_medias_normalizes_missing_episode_list_for_intersection():
    core = DownloadCore.__new__(DownloadCore)
    core._filetransfer = MagicMock()
    core._filetransfer.get_no_exists_medias.return_value = [1, 2, 3]
    media = MagicMock()
    media.type = ProviderMediaType.SERIES
    media.total_episodes = 0
    media.series_key = None
    media.tmdb_id = 123
    media.anchor_provider = None
    media.get_season_seq.return_value = "1"

    exists, missing, _ = core.check_exists_medias(media, total_ep={1: 10})

    assert exists is False
    assert missing == {"tmdb:123": [{"season": "1", "episodes": [1, 2, 3], "total_episodes": 10}]}
    target = {"tmdb:123": [{"season": "1", "episodes": [1, 2, 3]}]}
    result = Torrent.get_intersection_episodes(target=target, source=missing, title="tmdb:123")
    assert result["tmdb:123"][0]["episodes"] == [1, 2, 3]

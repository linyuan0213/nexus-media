"""DownloadCore 媒体库存在性检查回归测试."""

from unittest.mock import MagicMock

import pytest

from app.domain.mediatypes import MediaType
from app.services.download_core import DownloadCore


@pytest.mark.parametrize("total_ep", [{1: 10}, {"1": 10}])
@pytest.mark.parametrize("season", [1, "1"])
def test_check_exists_medias_accepts_numeric_or_string_season_keys(total_ep, season):
    core = DownloadCore.__new__(DownloadCore)
    core._filetransfer = MagicMock()
    core._filetransfer.get_no_exists_medias.return_value = []
    media = MagicMock()
    media.type = MediaType.TV
    media.total_episodes = 0
    media.get_season_seq.return_value = season

    exists, missing, _ = core.check_exists_medias(media, total_ep=total_ep)

    assert exists is True
    assert missing == {}
    core._filetransfer.get_no_exists_medias.assert_called_once_with(media, season=season, total_num=10)

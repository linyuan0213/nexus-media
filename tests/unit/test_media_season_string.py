"""电影不应输出季号."""

from app.domain.media_types import ProviderMediaType
from app.media.models import MediaInfo


def test_movie_season_string_is_empty():
    media = MediaInfo(title="Demo", type=ProviderMediaType.MOVIE)
    media.begin_season = 1
    assert media.get_season_string() == ""
    assert media.get_season_episode_string() == ""


def test_tv_season_string_keeps_season():
    media = MediaInfo(title="Demo", type=ProviderMediaType.SERIES)
    media.begin_season = 2
    assert media.get_season_string() == "S02"

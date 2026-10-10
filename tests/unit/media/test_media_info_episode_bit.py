"""季集补齐位数：单季超过 99 集时统一用 3 位集号，保证文件名排序."""

from app.domain.mediatypes import MediaType
from app.media import MediaInfo


def _tv(season: int = 1, begin: int | None = None, end: int | None = None) -> MediaInfo:
    return MediaInfo(
        type=MediaType.TV,
        begin_season=season,
        begin_episode=begin,
        end_episode=end,
    )


class TestEpisodeBit:
    def test_default_two_digits(self):
        assert _tv(begin=5).get_episode_bit() == 2

    def test_episode_over_99_uses_three_digits(self):
        assert _tv(begin=100).get_episode_bit() == 3

    def test_range_end_over_99_uses_three_digits(self):
        assert _tv(begin=98, end=105).get_episode_bit() == 3

    def test_total_episodes_over_99_uses_three_digits(self):
        media = _tv(begin=5)
        media.total_episodes = 100
        assert media.get_episode_bit() == 3

    def test_tmdb_season_episode_count_drives_bit(self):
        media = _tv(season=1, begin=5)
        media.tmdb_info = {"seasons": [{"season_number": 1, "episode_count": 120}]}
        assert media.get_episode_bit() == 3

    def test_tmdb_other_season_ignored(self):
        media = _tv(season=1, begin=5)
        media.tmdb_info = {"seasons": [{"season_number": 2, "episode_count": 120}]}
        assert media.get_episode_bit() == 2

    def test_movie_has_no_episode_bit_impact(self):
        media = MediaInfo(type=MediaType.MOVIE)
        assert media.get_episode_bit() == 2


class TestEpisodeRendering:
    def test_two_digit_keeps_legacy_episode_output(self):
        media = _tv(begin=5)
        assert media.get_episode_seqs() == "5"
        assert media.get_episode_items() == "E05"
        assert media.get_episode_string() == "E05"
        assert media.get_season_episode_string() == "S01 E05"

    def test_three_digit_single_episode(self):
        media = _tv(begin=100)
        assert media.get_episode_seqs() == "100"
        assert media.get_episode_items() == "E100"
        assert media.get_season_episode_string() == "S01 E100"

    def test_three_digit_range_consistent_padding(self):
        media = _tv(begin=98, end=105)
        assert media.get_episode_seqs() == "098-105"
        assert media.get_episode_items() == "E098E099E100E101E102E103E104E105"
        assert media.get_episode_string() == "E098-E105"

    def test_three_digit_uniform_within_season(self):
        # 同季低集号也应补齐到 3 位（TMDB 季集数 120）
        media = _tv(season=1, begin=5)
        media.tmdb_info = {"seasons": [{"season_number": 1, "episode_count": 120}]}
        assert media.get_episode_seqs() == "005"
        assert media.get_episode_items() == "E005"
        assert media.get_season_episode_string() == "S01 E005"

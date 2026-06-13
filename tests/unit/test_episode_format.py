"""EpisodeFormat 单元测试"""

from app.utils.episode_format import EpisodeFormat


class TestEpisodeFormat:
    def test_no_format_always_matches(self):
        fmt = EpisodeFormat("")
        assert fmt.match("anything.mkv") is True

    def test_match_simple_episode(self):
        fmt = EpisodeFormat("S01E{ep}", details="1-3")
        assert fmt.match("S01E02") is True

    def test_match_out_of_range(self):
        fmt = EpisodeFormat("S01E{ep}", details="1-3")
        assert fmt.match("S01E05") is False

    def test_match_no_details(self):
        fmt = EpisodeFormat("S01E{ep}")
        assert fmt.match("S01E99") is True

    def test_match_wrong_format(self):
        fmt = EpisodeFormat("S01E{ep}", details="1-3")
        assert fmt.match("Episode.02") is False

    def test_split_episode_range(self):
        fmt = EpisodeFormat("E{ep}", details="1-5")
        s, e, part = fmt.split_episode("E03-04")
        assert s == 3
        assert e == 4
        assert part is None

    def test_split_episode_single(self):
        fmt = EpisodeFormat("E{ep}", details="5")
        s, e, part = fmt.split_episode("E05")
        assert s == 5
        assert e is None

    def test_split_episode_offset(self):
        fmt = EpisodeFormat("E{ep}", details="1-5", offset=10)
        s, e, _ = fmt.split_episode("E03")
        assert s == 13

    def test_split_episode_no_format(self):
        fmt = EpisodeFormat("")
        assert fmt.split_episode("foo.mkv") == (None, None, None)

    def test_details_range(self):
        fmt = EpisodeFormat("E{ep}", details="10-20")
        assert fmt.start_ep == 10
        assert fmt.end_ep == 20

    def test_details_comma(self):
        fmt = EpisodeFormat("E{ep}", details="5,15")
        assert fmt.start_ep == 5
        assert fmt.end_ep == 15

    def test_details_single(self):
        fmt = EpisodeFormat("E{ep}", details="8")
        assert fmt.start_ep == 8
        assert fmt.end_ep == 8

    def test_part_property(self):
        fmt = EpisodeFormat("E{ep}", part="A")
        assert fmt.part == "A"

    def test_offset_property(self):
        fmt = EpisodeFormat("E{ep}", offset="3")
        assert fmt.offset == 3

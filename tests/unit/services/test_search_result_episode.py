"""搜索结果季集补全：ES_STRING 只有季时从标题推断集数."""

from types import SimpleNamespace

from app.domain.episode_utils import infer_episode_key
from app.domain.media_types import ProviderMediaType
from app.services.search_service import SearchResultProcessor


class TestInferEpisodeKey:
    def test_dash_episode(self):
        title = "[黒ネズミたち] 乱世千金 / Kyouran Reijou Nia Liston - 03 (ABEMA 1920x1080 x264 AAC)"
        assert infer_episode_key("S01", title) == "S01 E03"

    def test_explicit_episode(self):
        assert infer_episode_key("S01", "[ANi] 番剧 - 12 [1080P]") == "S01 E12"
        assert infer_episode_key("S02", "Show S02E07 1080p") == "S02 E07"

    def test_chinese_episode(self):
        assert infer_episode_key("S01", "某番 第8集 1080P") == "S01 E08"
        assert (
            infer_episode_key("S01", "[绿茶字幕组] 相反的你我 / Seihantai na Kimi to Boku [05][WebRip][1080p]")
            == "S01 E05"
        )
        assert infer_episode_key("S01", "某番 [1080p][WebRip]") == "S01"

    def test_keep_existing_episode_and_movie(self):
        assert infer_episode_key("S01 E05", "show - 09") == "S01 E05"
        assert infer_episode_key("movie", "movie - 03") == "movie"

    def test_no_episode(self):
        assert infer_episode_key("S01", "某番 1080P 合集") == "S01"


def test_fill_missing_episode_uses_shared_parser():
    item = SimpleNamespace(
        type=ProviderMediaType.SERIES,
        begin_episode=None,
        begin_season=None,
        total_episodes=1,
        org_string="[绿茶字幕组] 相反的你我 / Seihantai na Kimi to Boku [05][WebRip][1080p]",
        title="相反的你我",
    )

    SearchResultProcessor.fill_missing_episode(item)

    assert item.begin_episode == 5
    assert item.begin_season == 1

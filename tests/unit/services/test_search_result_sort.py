"""搜索结果排序：站点优先后必须先比做种数，再做规则顺序."""

from app.domain.mediatypes import MediaType
from app.media.models import MediaInfo
from app.services.search_service import SearchResultProcessor


def _movie(title: str, *, site_order: int, seeders: int, res_order: int) -> MediaInfo:
    media = MediaInfo(title=title, type=MediaType.MOVIE)
    media.site_order = site_order
    media.seeders = seeders
    media.res_order = res_order
    return media


class TestSearchResultSort:
    def test_site_mode_same_site_prefers_more_seeders(self):
        low_seed = _movie("LowSeed", site_order=9999, seeders=5, res_order=99)
        high_seed = _movie("HighSeed", site_order=9999, seeders=500, res_order=1)

        result = SearchResultProcessor.sort_results([low_seed, high_seed], download_order="site")

        assert result[0] is high_seed

    def test_site_mode_prefers_higher_priority_site(self):
        preferred = _movie("Preferred", site_order=9999, seeders=5, res_order=1)
        other = _movie("Other", site_order=0, seeders=500, res_order=99)

        result = SearchResultProcessor.sort_results([other, preferred], download_order="site")

        assert result[0] is preferred

    def test_seeder_mode_ignores_site_priority(self):
        low_seed = _movie("LowSeedPreferredSite", site_order=9999, seeders=5, res_order=99)
        high_seed = _movie("HighSeedOtherSite", site_order=0, seeders=500, res_order=1)

        result = SearchResultProcessor.sort_results([low_seed, high_seed], download_order="seeder")

        assert result[0] is high_seed

"""内置 provider 映射适配器测试（无网络）."""

from app.domain.mediatypes import MediaType
from app.media.metadata import ProviderRef, SearchQuery
from app.media.metadata.providers import (
    douban_detail_to_record,
    parse_runtime,
    pick_release_date,
    tmdb_detail_to_record,
)


def _tmdb_movie() -> dict:
    return {
        "id": 278,
        "title": "肖申克的救赎",
        "original_title": "The Shawshank Redemption",
        "release_date": "1994-09-23",
        "runtime": 142,
        "overview": "简介",
        "tagline": "希望让人自由",
        "original_language": "en",
        "origin_country": ["US"],
        "spoken_languages": [{"name": "English"}],
        "genres": [{"id": 18, "name": "剧情"}, {"id": 80, "name": "犯罪"}],
        "production_companies": [{"name": "Castle Rock Entertainment"}],
        "vote_average": 8.733,
        "vote_count": 31616,
        "popularity": 100.5,
        "status": "Released",
        "imdb_id": "tt0111161",
        "external_ids": {"wikidata_id": "Q172241"},
        "alternative_titles": {"titles": [{"iso_3166_1": "HK", "title": "月黑高飛", "type": ""}]},
        "translations": {
            "translations": [
                {"iso_639_1": "en", "data": {"title": "The Shawshank Redemption"}},
            ]
        },
        "poster_path": "/poster.jpg",
        "backdrop_path": "/backdrop.jpg",
        "images": {"logos": [{"file_path": "/logo.png", "iso_639_1": "zh"}]},
        "credits": {
            "cast": [{"id": 1, "name": "蒂姆·罗宾斯", "character": "Andy", "order": 0, "profile_path": "/a.jpg"}],
            "crew": [{"id": 2, "name": "弗兰克·德拉邦特", "job": "Director", "profile_path": None}],
        },
    }


def _tmdb_tv() -> dict:
    return {
        "id": 100088,
        "name": "最后生还者",
        "original_name": "The Last of Us",
        "first_air_date": "2023-01-15",
        "episode_run_time": [81],
        "overview": "剧集简介",
        "origin_country": ["US"],
        "spoken_languages": [{"name": "English"}],
        "genres": [{"name": "剧情"}],
        "networks": [{"name": "HBO"}],
        "vote_average": 8.6,
        "vote_count": 1000,
        "seasons": [
            {
                "season_number": 1,
                "name": "第一季",
                "episode_count": 9,
                "air_date": "2023-01-15",
                "poster_path": "/s1.jpg",
            }
        ],
    }


def test_tmdb_movie_mapping():
    record = tmdb_detail_to_record(
        _tmdb_movie(),
        media_type=MediaType.MOVIE,
        locale="zh-CN",
        image_url=lambda path: f"https://image{path}",
    )

    assert record.provider == "tmdb"
    assert record.external_id == "278"
    assert record.title == "肖申克的救赎"
    assert record.year == "1994"
    assert record.runtime == 142
    assert record.ratings == {"tmdb": 8.733}
    assert "月黑高飛" in record.aliases
    assert "The Shawshank Redemption" in record.aliases
    assert record.genres == ["剧情", "犯罪"]
    assert record.studios == ["Castle Rock Entertainment"]
    assert record.images["poster"][0].url == "https://image/poster.jpg"
    assert record.images["logo"][0].locale == "zh"
    assert {(ref.provider, ref.external_id) for ref in record.refs} == {
        ("tmdb", "278"),
        ("imdb", "tt0111161"),
        ("wikidata", "Q172241"),
    }
    assert [credit.name for credit in record.credits] == ["蒂姆·罗宾斯", "弗兰克·德拉邦特"]
    assert record.extra["tmdb.vote_count"] == 31616


def test_tmdb_tv_mapping_uses_name_and_networks():
    record = tmdb_detail_to_record(_tmdb_tv(), media_type=MediaType.TV)

    assert record.title == "最后生还者"
    assert record.release_date == "2023-01-15"
    assert record.runtime == 81
    assert record.labels == ["HBO"]
    assert record.seasons[0].episode_count == 9


def _douban_info() -> dict:
    return {
        "id": "1292052",
        "title": "肖申克的救赎",
        "original_title": "The Shawshank Redemption",
        "aka": ["月黑高飞(港)", "刺激1995(台)"],
        "year": "1994",
        "pubdate": ["2026-08-28(中国大陆)", "1994-09-23(美国)"],
        "durations": ["142分钟"],
        "intro": "中文简介",
        "countries": ["美国"],
        "languages": ["英语"],
        "genres": ["剧情", "犯罪"],
        "rating": {"value": 9.7, "count": 3351906},
        "cover_url": "https://img/douban.jpg",
        "comment_count": 668637,
        "review_count": 10000,
        "directors": [{"id": "1001", "name": "弗兰克·德拉邦特"}],
        "actors": [{"id": "1002", "name": "蒂姆·罗宾斯"}],
        "honor_infos": [{"title": "豆瓣电影Top250", "rank": 1}],
    }


def test_douban_mapping_and_release_date_guard():
    record = douban_detail_to_record(_douban_info(), media_type=MediaType.MOVIE)

    assert record.title == "肖申克的救赎"
    assert record.aliases == ["月黑高飞(港)", "刺激1995(台)"]
    # 2026 重映日被过滤，取 1994 原始日期
    assert record.release_date == "1994-09-23"
    assert record.runtime == 142
    assert record.ratings == {"douban": 9.7}
    assert record.images["poster"][0].url == "https://img/douban.jpg"
    assert [credit.role for credit in record.credits] == ["director", "actor"]
    assert record.extra["douban.comment_count"] == 668637


def test_douban_release_date_none_when_only_rerelease():
    assert pick_release_date(["2026-08-28(中国大陆)"], "1994") is None
    assert pick_release_date(["1994-09-23(美国)"], "1994") == "1994-09-23"
    assert pick_release_date([], "1994") is None


def test_parse_runtime_with_range_and_invalid():
    assert parse_runtime(["44-81分钟"]) == 44
    assert parse_runtime(["142分钟"]) == 142
    assert parse_runtime([]) is None
    assert parse_runtime("142分钟") is None


class _FakeTmdbDetail:
    def __init__(self, info):
        self._info = info

    def get_detail(self, tmdbid, mtype, language=None, append_to_response=None):
        return self._info


class _FakeTmdbSeason:
    def get_episodes(self, tmdbid, season):
        # 现有 TmdbSeason 返回倒序
        return [
            {"season_number": season, "episode_number": 2, "name": "第二集", "runtime": 53},
            {"season_number": season, "episode_number": 1, "name": "第一集", "runtime": 81},
        ]


class _FakeTmdbSearch:
    def search_movie_infos(self, name, year=None):
        return [{"id": 278, "title": "肖申克的救赎", "release_date": "1994-09-23", "popularity": 10}]

    def search_tv_infos(self, name, year=None):
        return []


class _FakeDoubanApi:
    def __init__(self, info):
        self._info = info

    def search(self, keyword, start=0, count=20, ts=None):
        return {"items": []}

    def movie_detail(self, subject_id):
        return self._info

    def tv_detail(self, subject_id):
        return self._info


class _FakeBangumi:
    def __init__(self, info):
        self._info = info

    def detail(self, bid):
        return self._info

    def search(self, keyword, page=1, limit=20, subject_type=2):
        return []


def test_tmdb_provider_adapter_maps_detail_and_episodes():
    from app.media.metadata.providers import TmdbProvider

    provider = TmdbProvider(
        detail=_FakeTmdbDetail(_tmdb_tv()),
        season=_FakeTmdbSeason(),
        search=_FakeTmdbSearch(),
    )
    record = provider.detail(
        ProviderRef(provider="tmdb", external_id="100088", media_type=MediaType.TV),
        None,
    )

    assert record is not None
    assert record.title == "最后生还者"
    assert [episode.episode_number for episode in record.episodes] == [1, 2]
    assert (
        provider.seasons(
            ProviderRef(provider="tmdb", external_id="100088", media_type=MediaType.TV),
            None,
        )[0].episode_count
        == 9
    )


def test_douban_provider_adapter_uses_frodo_detail():
    from app.media.metadata.providers import DoubanProvider

    provider = DoubanProvider(api=_FakeDoubanApi(_douban_info()))
    record = provider.detail(
        ProviderRef(provider="douban", external_id="1292052", media_type=MediaType.MOVIE),
        None,
    )

    assert record is not None
    assert record.title == "肖申克的救赎"
    assert record.release_date == "1994-09-23"
    assert record.ratings == {"douban": 9.7}


def test_bangumi_provider_adapter_maps_subject():
    from app.media.metadata.providers import BangumiProvider

    info = {
        "id": 400602,
        "name": "Tenmaku no Jaadugar",
        "name_cn": "穹庐下的魔女",
        "summary": "简介",
        "date": "2025-01-05",
        "images": {"large": "https://img/bgm.jpg"},
        "rating": {"score": 8.2, "rank": 100, "total": 500},
        "tags": [{"name": "TV"}, {"name": "奇幻"}],
        "infobox": [
            {"key": "动画制作", "value": "某工作室"},
            {"key": "英文名", "value": "The Witch of the Tenmaku"},
        ],
    }
    provider = BangumiProvider(client=_FakeBangumi(info))
    record = provider.detail(ProviderRef(provider="bangumi", external_id="400602"), None)

    assert record is not None
    assert record.title == "穹庐下的魔女"
    assert record.year == "2025"
    assert record.ratings == {"bangumi": 8.2}
    assert record.studios == ["某工作室"]
    assert "The Witch of the Tenmaku" in record.aliases
    assert record.images["poster"][0].url == "https://img/bgm.jpg"


class _FakeEpisodeScraper:
    def fetch(self, subject_id, season=1):
        return (
            {
                "season_number": season,
                "episode_number": 1,
                "title": "第一集",
                "air_date": "2023-01-15",
                "overview": "简介",
                "still": "https://img/still.jpg",
            },
        )


def test_douban_provider_attaches_html_episodes():
    from app.media.metadata.providers import DoubanProvider

    provider = DoubanProvider(api=_FakeDoubanApi(_douban_info()), episode_scraper=_FakeEpisodeScraper())
    episodes = provider.episodes(
        ProviderRef(provider="douban", external_id="1292052", media_type=MediaType.TV),
        1,
        None,
    )

    assert len(episodes) == 1
    assert episodes[0].title == "第一集"
    assert episodes[0].air_date == "2023-01-15"


def test_bangumi_provider_search_maps_results():
    from app.media.metadata.providers import BangumiProvider

    class _FakeBangumiSearch:
        def search(self, keyword, page=1, limit=20, subject_type=2):
            return [
                {
                    "id": 328609,
                    "name": "ぼっち・ざ・ろっく！",
                    "name_cn": "孤独摇滚！",
                    "date": "2022-10-09",
                    "images": {"large": "https://img/bgm.jpg"},
                    "rating": {"score": 8.7},
                }
            ]

        def detail(self, bid):
            return {}

    hits = BangumiProvider(client=_FakeBangumiSearch()).search(SearchQuery(query="孤独摇滚"), None)

    assert len(hits) == 1
    assert hits[0].title == "孤独摇滚！"
    assert hits[0].year == "2022"
    assert hits[0].ref.external_id == "328609"

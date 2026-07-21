"""SubscribeMatcher 单元测试."""

from unittest.mock import MagicMock

import pytest

from app.domain.mediatypes import MediaType
from app.services.subscribe.matcher import SubscribeMatcher


def _make_media_info(mtype, title, year, tmdb_id=None):
    media_info = MagicMock()
    media_info.type = mtype
    media_info.title = title
    media_info.year = year
    media_info.tmdb_id = tmdb_id
    media_info.rev_string = title
    media_info.org_string = f"{title} {year}"
    media_info.get_name.return_value = title
    media_info.get_title_string.return_value = title
    media_info.get_season_string.return_value = "S01"
    media_info.get_season_episode_string.return_value = "S01 E01"
    media_info.site = "test_site"
    media_info.subtitle = ""
    return media_info


@pytest.fixture
def matcher():
    return SubscribeMatcher()


class TestSubscribeMatcher:
    def test_movie_torrent_does_not_match_tv_subscription(self, matcher):
        """电影种子不应匹配电视剧订阅."""
        media_info = _make_media_info(MediaType.MOVIE, "攻壳机动队", "1995")
        rss_tvs = {
            1: {
                "name": "攻壳机动队",
                "year": "2026",
                "season": "S01",
                "tmdbid": None,
                "fuzzy_match": False,
            }
        }

        match_flag, match_msg, match_info = matcher.match(
            media_info=media_info,
            rss_movies={},
            rss_tvs=rss_tvs,
            site_id="test_site",
            site_filter_rule=None,
            site_cookie="",
            site_parse=False,
            site_ua="",
            site_headers={},
            site_proxy=False,
        )
        assert match_flag is False

    def test_tv_torrent_matches_tv_subscription(self, matcher):
        """电视剧种子应匹配同名同年份电视剧订阅."""
        media_info = _make_media_info(MediaType.TV, "攻壳机动队", "2026")
        rss_tvs = {
            1: {
                "name": "攻壳机动队",
                "year": "2026",
                "season": "S01",
                "tmdbid": None,
                "fuzzy_match": False,
            }
        }

        match_flag, match_msg, match_info = matcher.match(
            media_info=media_info,
            rss_movies={},
            rss_tvs=rss_tvs,
            site_id="test_site",
            site_filter_rule=None,
            site_cookie="",
            site_parse=False,
            site_ua="",
            site_headers={},
            site_proxy=False,
        )
        assert match_flag is True
        assert match_info["name"] == "攻壳机动队"

    def test_anime_torrent_matches_tv_subscription(self, matcher):
        """动漫种子应匹配电视剧订阅."""
        media_info = _make_media_info(MediaType.ANIME, "攻壳机动队", "2026")
        rss_tvs = {
            1: {
                "name": "攻壳机动队",
                "year": "2026",
                "season": "S01",
                "tmdbid": None,
                "fuzzy_match": False,
            }
        }

        match_flag, match_msg, match_info = matcher.match(
            media_info=media_info,
            rss_movies={},
            rss_tvs=rss_tvs,
            site_id="test_site",
            site_filter_rule=None,
            site_cookie="",
            site_parse=False,
            site_ua="",
            site_headers={},
            site_proxy=False,
        )
        assert match_flag is True
        assert match_info["name"] == "攻壳机动队"

    def test_movie_torrent_matches_movie_subscription(self, matcher):
        """电影种子应匹配电影订阅."""
        media_info = _make_media_info(MediaType.MOVIE, "攻壳机动队", "1995")
        rss_movies = {
            1: {
                "name": "攻壳机动队",
                "year": "1995",
                "tmdbid": None,
                "fuzzy_match": False,
            }
        }

        match_flag, match_msg, match_info = matcher.match(
            media_info=media_info,
            rss_movies=rss_movies,
            rss_tvs={},
            site_id="test_site",
            site_filter_rule=None,
            site_cookie="",
            site_parse=False,
            site_ua="",
            site_headers={},
            site_proxy=False,
        )
        assert match_flag is True
        assert match_info["name"] == "攻壳机动队"

    def test_tv_torrent_does_not_match_movie_subscription(self, matcher):
        """电视剧种子不应匹配电影订阅."""
        media_info = _make_media_info(MediaType.TV, "攻壳机动队", "2026")
        rss_movies = {
            1: {
                "name": "攻壳机动队",
                "year": "1995",
                "tmdbid": None,
                "fuzzy_match": False,
            }
        }

        match_flag, match_msg, match_info = matcher.match(
            media_info=media_info,
            rss_movies=rss_movies,
            rss_tvs={},
            site_id="test_site",
            site_filter_rule=None,
            site_cookie="",
            site_parse=False,
            site_ua="",
            site_headers={},
            site_proxy=False,
        )
        assert match_flag is False

"""媒体库平铺/分类两种目录结构测试."""

import pytest

from app.domain.mediatypes import MediaType
from app.media.models import MediaInfo
from app.services.media_config_service import MediaConfigService
from app.services.transfer.existence_checker import MediaExistenceChecker
from app.services.transfer.path_resolver import TransferPathResolver


def _resolver(**kwargs):
    return TransferPathResolver(
        movie_path=["/media/movie"],
        tv_path=["/media/tv"],
        anime_path=["/media/anime"],
        movie_dir_rmt_format="{title} ({year})",
        movie_file_rmt_format="{title}",
        tv_dir_rmt_format="{title} ({year})",
        tv_season_rmt_format="Season {season}",
        tv_file_rmt_format="{title} - S{season:02d}E{episode:02d}",
        **kwargs,
    )


def _media(media_type, category="分类", title="作品", season=1):
    return MediaInfo(
        type=media_type,
        category=category,
        title=title,
        year="2024",
        begin_season=season,
        begin_episode=1,
        end_episode=1,
        org_string=f"{title}.S01E01.mkv",
        rev_string=f"{title}.S01E01.mkv",
    )


@pytest.mark.parametrize(
    ("media_type", "flag", "expected"),
    [
        (MediaType.MOVIE, True, "/media/movie/分类/作品 (2024)"),
        (MediaType.MOVIE, False, "/media/movie/作品 (2024)"),
        (MediaType.TV, True, "/media/tv/分类/作品 (2024)/Season 1"),
        (MediaType.TV, False, "/media/tv/作品 (2024)/Season 1"),
    ],
)
def test_movie_tv_category_layout(media_type, flag, expected):
    resolver = _resolver(
        movie_category_flag=flag,
        tv_category_flag=flag,
    )
    root = "/media/movie" if media_type == MediaType.MOVIE else "/media/tv"
    assert resolver.get_dest_path_by_info(root, _media(media_type), None) == expected


@pytest.mark.parametrize(
    ("flag", "category", "expected"),
    [
        (False, "分类", "/media/anime/作品 (2024)/Season 1"),
        (True, "分类", "/media/anime/分类/作品 (2024)/Season 1"),
        (True, "", "/media/anime/作品 (2024)/Season 1"),
    ],
)
def test_anime_layout_defaults_to_flat(flag, category, expected):
    resolver = _resolver(anime_category_flag=flag)
    assert resolver.get_dest_path_by_info("/media/anime", _media(MediaType.ANIME, category=category), None) == expected


def test_existence_checker_keeps_legacy_layout_compatible():
    assert MediaExistenceChecker._layout_dirs("/anime", "作品 (2024)", "分类", False) == [
        "/anime/作品 (2024)",
        "/anime/分类/作品 (2024)",
    ]
    assert MediaExistenceChecker._layout_dirs("/anime", "作品 (2024)", "", False) == ["/anime/作品 (2024)"]


def test_invalid_category_name_falls_back_to_flat():
    resolver = _resolver(movie_category_flag=True)
    assert (
        resolver.get_dest_path_by_info("/media/movie", _media(MediaType.MOVIE, category="../escape"), None)
        == "/media/movie/作品 (2024)"
    )


def test_default_layouts_are_category_for_movie_tv_and_flat_for_anime():
    assert MediaConfigService._parse_layout(None, "movie") == "category"
    assert MediaConfigService._parse_layout(None, "tv") == "category"
    assert MediaConfigService._parse_layout(None, "anime") == "flat"

"""媒体库平铺/分类两种目录结构测试."""

import pytest

from app.domain.media_types import ProviderMediaType
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
        (ProviderMediaType.MOVIE, True, "/media/movie/分类/作品 (2024)"),
        (ProviderMediaType.MOVIE, False, "/media/movie/作品 (2024)"),
        (ProviderMediaType.SERIES, True, "/media/tv/分类/作品 (2024)/Season 1"),
        (ProviderMediaType.SERIES, False, "/media/tv/作品 (2024)/Season 1"),
    ],
)
def test_movie_tv_category_layout(media_type, flag, expected):
    resolver = _resolver(
        movie_category_flag=flag,
        tv_category_flag=flag,
    )
    root = "/media/movie" if media_type == ProviderMediaType.MOVIE else "/media/tv"
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
    assert (
        resolver.get_dest_path_by_info("/media/anime", _media(ProviderMediaType.ANIME, category=category), None)
        == expected
    )


def test_existence_checker_keeps_legacy_layout_compatible():
    assert MediaExistenceChecker._layout_dirs("/anime", "作品 (2024)", "分类", False) == [
        "/anime/作品 (2024)",
        "/anime/分类/作品 (2024)",
    ]
    assert MediaExistenceChecker._layout_dirs("/anime", "作品 (2024)", "", False) == ["/anime/作品 (2024)"]


def test_invalid_category_name_falls_back_to_flat():
    resolver = _resolver(movie_category_flag=True)
    assert (
        resolver.get_dest_path_by_info("/media/movie", _media(ProviderMediaType.MOVIE, category="../escape"), None)
        == "/media/movie/作品 (2024)"
    )


def test_default_layouts_are_category_for_movie_tv_and_flat_for_anime():
    assert MediaConfigService._parse_layout(None, "movie") == "category"
    assert MediaConfigService._parse_layout(None, "tv") == "category"
    assert MediaConfigService._parse_layout(None, "anime") == "flat"


def test_existence_checker_returns_category_dir_for_new_movie(tmp_path):
    """新文件必须落主布局（分类子目录），不能因为候选顺序落到平铺路径."""
    checker = MediaExistenceChecker(_resolver(movie_category_flag=True))
    media = _media(ProviderMediaType.MOVIE, category="华语电影", title="门牙")
    dir_exist, ret_dir, file_exist, ret_file = checker.is_media_exists(str(tmp_path), media)
    assert dir_exist is False
    assert file_exist is False
    assert ret_dir == str(tmp_path / "华语电影" / "门牙 (2024)")
    assert ret_file == str(tmp_path / "华语电影" / "门牙 (2024)" / "门牙")


def test_existence_checker_returns_flat_dir_for_new_movie_when_flat(tmp_path):
    checker = MediaExistenceChecker(_resolver(movie_category_flag=False))
    media = _media(ProviderMediaType.MOVIE, category="华语电影", title="门牙")
    dir_exist, ret_dir, file_exist, ret_file = checker.is_media_exists(str(tmp_path), media)
    assert dir_exist is False
    assert file_exist is False
    assert ret_dir == str(tmp_path / "门牙 (2024)")


def test_existence_checker_finds_legacy_flat_file(tmp_path):
    """旧平铺路径已存在文件时仍能命中，避免切换布局后重复入库."""
    flat_dir = tmp_path / "门牙 (2024)"
    flat_dir.mkdir()
    (flat_dir / "门牙.mkv").write_text("x")
    checker = MediaExistenceChecker(_resolver(movie_category_flag=True))
    media = _media(ProviderMediaType.MOVIE, category="华语电影", title="门牙")
    _, ret_dir, file_exist, ret_file = checker.is_media_exists(str(tmp_path), media)
    assert file_exist is True
    assert ret_dir == str(flat_dir)
    assert ret_file == str(flat_dir / "门牙.mkv")


def test_existence_checker_returns_category_season_dir_for_new_episode(tmp_path):
    checker = MediaExistenceChecker(_resolver(tv_category_flag=True))
    media = _media(ProviderMediaType.SERIES, category="国产剧", title="门牙")
    dir_exist, ret_dir, file_exist, _ = checker.is_media_exists(str(tmp_path), media)
    assert dir_exist is False
    assert file_exist is False
    assert ret_dir == str(tmp_path / "国产剧" / "门牙 (2024)" / "Season 1")


def test_existence_checker_anime_defaults_to_flat(tmp_path):
    resolver = _resolver(anime_category_flag=False)
    checker = MediaExistenceChecker(resolver)
    media = _media(ProviderMediaType.ANIME, category="动漫", title="门牙")
    _, ret_dir, file_exist, _ = checker.is_media_exists(str(tmp_path), media)
    assert file_exist is False
    assert ret_dir == str(tmp_path / "门牙 (2024)" / "Season 1")


def test_naming_profile_with_category_skips_generic_category(monkeypatch):
    from app.media.metadata.naming import NamingProfile
    from app.services.transfer import path_resolver

    monkeypatch.setattr(
        path_resolver,
        "list_naming_profiles",
        lambda: [NamingProfile(key="custom.default", content_profile="custom", provides_category=True)],
    )
    resolver = _resolver(movie_category_flag=True)
    media = _media(ProviderMediaType.MOVIE, category="通用分类", title="DEMO-138")
    media.content_profile = "custom"

    assert resolver.get_dest_path_by_info("/media/custom", media, None) == "/media/custom/DEMO-138 (2024)"

"""批量重命名元数据解析测试."""

from __future__ import annotations

from types import SimpleNamespace

from app.domain.media_types import ProviderMediaType
from app.media.models import MediaInfo
from app.services.transfer.library_rename_nfo import collect_nfo
from app.services.transfer.library_rename_sources import (
    apply_source,
    detect_part,
    from_download_history,
    from_filename,
    merge_missing,
    parse_season_episode,
)
from app.storage.backends.base import StorageType
from app.storage.backends.local import LocalStorageBackend
from app.storage.config_models import LocalStorageConfig


def _backend() -> LocalStorageBackend:
    return LocalStorageBackend(LocalStorageConfig(id="local", name="本地", type=StorageType.LOCAL))


def test_parse_season_episode_variants():
    assert parse_season_episode("S01 E01-E05") == (1, 1, 1, 5)
    assert parse_season_episode("S01-S02 E03") == (1, 2, 3, 3)
    assert parse_season_episode("S01E01E05") == (1, 1, 1, 5)
    assert parse_season_episode("movie") == (None, None, None, None)


def test_detect_part_and_apply_source():
    assert detect_part("Movie.2020.Part.1.1080p.mkv") == "Part 1"
    meta = MediaInfo(type=ProviderMediaType.MOVIE, title="Movie", year="2020")
    apply_source(meta, "Movie.2020.1080p.BluRay.x264-GROUP.mkv")
    assert meta.org_string == "Movie.2020.1080p.BluRay.x264-GROUP.mkv"
    assert meta.resource_pix == "1080p"
    assert meta.resource_type == "BluRay"
    assert meta.resource_team == "GROUP"


def test_merge_missing_does_not_override_identity():
    target = MediaInfo(type=ProviderMediaType.SERIES, title="历史标题", year="2020", tmdb_id=100)
    source = MediaInfo(type=ProviderMediaType.SERIES, title="另一个标题", year="2021", tmdb_id=200, imdb_id="tt1")
    merge_missing(target, source)
    assert target.title == "历史标题"
    assert target.tmdb_id == 100
    assert target.imdb_id == "tt1"


def test_nfo_tv_uses_series_tmdb_and_episode_fields(tmp_path):
    directory = tmp_path / "Show"
    directory.mkdir()
    (directory / "tvshow.nfo").write_text(
        "<tvshow><title>Show</title><year>2020</year><uniqueid type='tmdb'>100</uniqueid></tvshow>",
        encoding="utf-8",
    )
    (directory / "Show.S01E02.nfo").write_text(
        "<episodedetails><title>Pilot</title><season>1</season><episode>2</episode>"
        "<uniqueid type='tmdb'>999</uniqueid></episodedetails>",
        encoding="utf-8",
    )
    data = collect_nfo(_backend(), str(directory), "Show.S01E02", ProviderMediaType.SERIES)
    assert data is not None
    assert data["title"] == "Show"
    assert data["tmdbid"] == "100"
    assert data["episode_title"] == "Pilot"
    assert data["season"] == 1
    assert data["episode"] == 2


def test_nfo_tv_keeps_content_id_identity(tmp_path):
    directory = tmp_path / "Show"
    directory.mkdir()
    (directory / "tvshow.nfo").write_text(
        "<tvshow><title>Show</title><uniqueid type='content_id'>CUSTOM-0001</uniqueid></tvshow>",
        encoding="utf-8",
    )
    data = collect_nfo(_backend(), str(directory), "Show.S01E02", ProviderMediaType.SERIES)
    assert data is not None
    assert data["content_id"] == "CUSTOM-0001"
    assert data["unique_ids"]["content_id"] == "CUSTOM-0001"


def test_season_nfo_title_is_not_show_title(tmp_path):
    directory = tmp_path / "Show"
    directory.mkdir()
    (directory / "season.nfo").write_text(
        "<season><title>Season 1</title><seasonnumber>1</seasonnumber><year>2020</year></season>",
        encoding="utf-8",
    )
    data = collect_nfo(_backend(), str(directory), "Show.S01E02", ProviderMediaType.SERIES)
    assert data is not None
    assert "title" not in data
    assert data["season"] == 1


def test_from_download_history_sets_source_only_when_name_matches():
    entity = SimpleNamespace(
        media_type="movie",
        title="Movie",
        year="2020",
        tmdb_id="100",
        season_episode="",
        torrent="Movie.2020.1080p-GROUP.mkv",
    )
    matched = from_download_history(entity, "Movie.2020.1080p-GROUP.mkv", ProviderMediaType.MOVIE, exact=True)
    assert matched is not None
    assert matched.source_filename == "Movie.2020.1080p-GROUP.mkv"
    unmatched = from_download_history(entity, "Other.Name.mkv", ProviderMediaType.MOVIE, exact=False)
    assert unmatched is not None
    assert unmatched.source_filename is None


def test_from_filename_does_not_set_original_name():
    resolved = from_filename("/library/The.Matrix.1999.1080p.BluRay.x264-GROUP.mkv", ProviderMediaType.MOVIE)
    assert resolved is not None
    assert resolved.media.org_string is None
    assert resolved.media.rev_string is None

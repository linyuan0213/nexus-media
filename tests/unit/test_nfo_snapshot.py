"""快照驱动 NFO 渲染测试（无网络）."""

from datetime import datetime, timezone
from typing import Any, cast

import pytest

from app.domain.mediatypes import MediaType
from app.media.metadata import (
    Credit,
    EpisodeRecord,
    FieldValue,
    MediaMetadata,
    ProviderRef,
    SeasonRecord,
)
from app.media.scraper.nfo_generator import NfoGenerator


class _FakeDownloader:
    def __init__(self):
        self.saved = []

    def save_nfo(self, doc, path):
        self.saved.append((doc.toxml(), path))


def _snapshot(**overrides) -> MediaMetadata:
    data = {
        "identity_id": "01J00000000000000000000000",
        "media_type": MediaType.MOVIE,
        "content_profile": "default",
        "primary_provider": "douban",
        "refs": [
            ProviderRef(provider="douban", external_id="1292052"),
            ProviderRef(provider="tmdb", external_id="278"),
            ProviderRef(provider="imdb", external_id="tt0111161"),
        ],
        "fields": {
            "title": FieldValue(value="肖申克的救赎", provider="douban", external_id="1292052"),
            "original_title": FieldValue(value="The Shawshank Redemption", provider="tmdb", external_id="278"),
            "year": FieldValue(value="1994", provider="tmdb", external_id="278"),
            "release_date": FieldValue(value="1994-09-23", provider="tmdb", external_id="278"),
            "overview": FieldValue(value="中文简介", provider="douban", external_id="1292052"),
        },
        "genres": ["剧情", "犯罪"],
        "ratings": {"douban": 9.7, "tmdb": 8.7},
        "credits": [
            Credit(name="弗兰克·德拉邦特", role="director", provider="tmdb", external_id="1"),
            Credit(name="蒂姆·罗宾斯", role="actor", character="Andy", order=0, provider="tmdb", external_id="2"),
        ],
        "fetched_at": datetime.now(timezone.utc),
    }
    data.update(overrides)
    return MediaMetadata(**data)


def test_movie_nfo_from_snapshot_writes_primary_uniqueid_and_credits(tmp_path):
    downloader = _FakeDownloader()
    generator = NfoGenerator(downloader)
    snapshot = _snapshot()

    generator.gen_movie_nfo_from_snapshot(
        snapshot,
        {"basic": True, "credits": True},
        str(tmp_path),
        "movie",
    )

    xml, path = downloader.saved[0]
    assert path.endswith("movie.nfo")
    assert "<title>肖申克的救赎</title>" in xml
    assert '<uniqueid type="douban" default="true">1292052</uniqueid>' in xml
    assert '<uniqueid type="tmdb" default="false">278</uniqueid>' in xml
    assert "<tmdbid>278</tmdbid>" in xml
    assert "<imdbid>tt0111161</imdbid>" in xml
    assert "<genre>剧情</genre>" in xml
    assert "<rating>9.7</rating>" in xml
    assert "<director" in xml and "弗兰克·德拉邦特" in xml
    assert "<name>蒂姆·罗宾斯</name>" in xml


def test_tv_season_and_episode_nfo_from_snapshot(tmp_path):
    downloader = _FakeDownloader()
    generator = NfoGenerator(downloader)
    snapshot = _snapshot(
        media_type=MediaType.TV,
        primary_provider="tmdb",
        seasons=[SeasonRecord(season_number=1, title="第一季", air_date="2023-01-15", episode_count=9)],
        episodes=[
            EpisodeRecord(
                season_number=1,
                episode_number=1,
                title="迷失在黑暗之中",
                air_date="2023-01-15",
                runtime=81,
                vote_average=8.0,
                overview="第一集简介",
            )
        ],
    )

    generator.gen_tv_nfo_from_snapshot(snapshot, {"basic": True}, str(tmp_path))
    generator.gen_season_nfo_from_snapshot(snapshot.seasons[0], 1, str(tmp_path))
    generator.gen_episode_nfo_from_snapshot(
        snapshot, snapshot.episodes[0], {"episode_basic": True}, 1, str(tmp_path), "S01E01"
    )

    paths = [path for _, path in downloader.saved]
    assert any(path.endswith("tvshow.nfo") for path in paths)
    assert any(path.endswith("season.nfo") for path in paths)
    episode_xml = next(xml for xml, path in downloader.saved if path.endswith("S01E01.nfo"))
    assert "<title>迷失在黑暗之中</title>" in episode_xml
    assert "<season>1</season>" in episode_xml
    assert "<episode>1</episode>" in episode_xml


def test_scraper_snapshot_movie_path_writes_nfo(tmp_path):
    from app.media.scraper import Scraper

    downloader = _FakeDownloader()
    scraper = Scraper.__new__(Scraper)
    scraper._scraper_nfo = {"movie": {"basic": True, "credits": True}}
    scraper._scraper_pic = {}
    scraper._dst_backend = None
    scraper._metadata_service = None
    scraper._downloader = cast(Any, downloader)
    scraper._nfo_gen = NfoGenerator(downloader)

    scraper._scrape_movie_from_snapshot(_snapshot(), str(tmp_path), "movie", True, False)

    assert downloader.saved
    assert downloader.saved[0][1].endswith("movie.nfo")


def test_snapshot_image_download_falls_back_to_next_candidate(tmp_path):
    from app.media.metadata import ImageAsset, ImageResolver
    from app.media.scraper import Scraper

    class _FallbackDownloader(_FakeDownloader):
        def __init__(self):
            super().__init__()
            self.attempts = []

        def download(self, url, out_path, itype="", force=False):
            self.attempts.append(url)
            return url != "bad"

    downloader = _FallbackDownloader()
    scraper = Scraper.__new__(Scraper)
    scraper._downloader = cast(Any, downloader)
    scraper._dst_backend = None
    scraper._images = ImageResolver()
    snapshot = _snapshot(
        images={
            "poster": [
                ImageAsset(type="poster", url="bad", width=1000, height=1500, provider="douban"),
                ImageAsset(type="poster", url="good", width=800, height=1200, provider="douban"),
            ]
        }
    )

    scraper._download_snapshot_images(snapshot, str(tmp_path), {"poster": True}, False)

    # 只尝试竖版候选；横版整张封套/剧照不再被裁成海报。
    assert downloader.attempts == ["bad", "good"]


def test_nfo_profile_extra_tags():
    from app.media.metadata.nfo import NfoProfile, register_nfo_profile, render_nfo_extra_tags
    from app.media.metadata.registry import MetadataRegistry

    registry = MetadataRegistry()
    register_nfo_profile(
        NfoProfile(key="demo-nfo", content_profile="default", extra_tags=lambda snapshot: {"tag": ["A", "B"]}),
        registry=registry,
        plugin_id="p-nfo",
    )

    snapshot = _snapshot()
    assert render_nfo_extra_tags(snapshot, registry=registry) == {"tag": ["A", "B"]}


def test_movie_nfo_writes_nested_ratings_and_votes(tmp_path):
    from app.media.metadata import ProviderDescriptor
    from app.media.metadata.registry import registry

    class _Provider:
        descriptor = ProviderDescriptor(provider_key="javdb", display_name="JavDB", rating_max=5)

    registry.register_provider(_Provider(), plugin_id="test")
    try:
        _run_movie_nfo_ratings_test(tmp_path)
    finally:
        registry.unregister_provider("javdb", plugin_id="test")


def _run_movie_nfo_ratings_test(tmp_path):
    downloader = _FakeDownloader()
    generator = NfoGenerator(downloader)
    snapshot = _snapshot(
        primary_provider="javdb",
        ratings={"javdb": 4.6, "douban": 8.8},
        fields={
            **_snapshot().fields,
            "votes": FieldValue(value="1234", provider="javdb", external_id="x"),
        },
    )

    generator.gen_movie_nfo_from_snapshot(
        snapshot,
        {"basic": True, "credits": False},
        str(tmp_path),
        "movie",
    )

    xml, _ = downloader.saved[0]
    assert "<votes>1234</votes>" in xml
    assert "<ratings>" in xml
    assert '<rating name="javdb" max="5" default="true">' in xml
    assert "<value>4.6</value>" in xml
    assert '<rating name="douban" max="10"' in xml


def test_movie_nfo_appends_real_streamdetails(tmp_path):
    import shutil
    from pathlib import Path

    source = Path("/tmp/nexus_e2e2/av-library/ABP-566/ABP-566-流出-cd1.mp4")
    if not source.exists():
        pytest.skip("缺少真实媒体样本")
    shutil.copy2(source, tmp_path / "sample.mp4")
    downloader = _FakeDownloader()
    generator = NfoGenerator(downloader)
    generator.gen_movie_nfo_from_snapshot(
        _snapshot(),
        {"basic": True, "credits": False},
        str(tmp_path),
        "sample",
    )
    xml, _ = downloader.saved[0]
    assert "<fileinfo>" in xml
    assert "<streamdetails>" in xml
    assert "<video>" in xml
    assert "<codec>" in xml


def test_movie_nfo_marks_external_subtitle_as_chinese(tmp_path):
    downloader = _FakeDownloader()
    generator = NfoGenerator(downloader)
    (tmp_path / "movie.chi.zh-cn.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\n字幕", encoding="utf-8")

    generator.gen_movie_nfo_from_snapshot(
        _snapshot(),
        {"basic": True, "credits": True},
        str(tmp_path),
        "movie",
    )

    xml, _ = downloader.saved[0]
    assert "<tag>中字</tag>" in xml

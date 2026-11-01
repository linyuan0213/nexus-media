"""IndexerFilterEngine 单元测试."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.domain.mediatypes import MediaType
from app.indexer.core.filter_engine import IndexerFilterEngine
from app.indexer.core.result_filter import ResultFilter


def _meta(title: str, subtitle: str | None = None):
    m = MagicMock()
    m.rev_string = title
    m.subtitle = subtitle
    m.org_string = title
    m.get_edtion_string.return_value = ""
    m.resource_pix = ""
    m.resource_team = ""
    return m


class TestBookFilter:
    @pytest.mark.parametrize(
        "title",
        [
            "あかね噺 raw 第13巻 あかね噺1-6 7-13巻相当2024年08月26日更新",
            "[漫画] あかね噺 第13巻",
            "あかね噺 Manga Vol.13",
            "あかね噺 コミック 第13巻",
        ],
    )
    def test_reject_manga_for_anime(self, title):
        meta = _meta(title)
        match, _, msg = IndexerFilterEngine.check_torrent_filter(meta, {"type": MediaType.ANIME})
        assert not match
        assert "漫画/书籍类资源" in msg

    def test_keep_anime_bdmv_volume(self):
        meta = _meta("あかね噺 第1巻 BD")
        match, _, _ = IndexerFilterEngine.check_torrent_filter(meta, {"type": MediaType.ANIME})
        assert match

    def test_keep_anime_episode(self):
        meta = _meta("Akane Banashi S01E12 1080p NF WEB-DL AAC2.0 H 264-VARYG")
        match, _, _ = IndexerFilterEngine.check_torrent_filter(meta, {"type": MediaType.ANIME})
        assert match

    def test_reject_raw_volume(self):
        meta = _meta("あかね噺 RAW 第13巻")
        match, _, _ = IndexerFilterEngine.check_torrent_filter(meta, {"type": MediaType.ANIME})
        assert not match


class TestAudioFilter:
    def test_video_with_flac_audio_is_not_rejected(self):
        meta = _meta("[DBD-Raws][肖申克的救赎/The Shawshank Redemption][1080P][BDRip][HEVC-10bit][中英外挂][FLAC][MKV]")
        match, _, _ = IndexerFilterEngine.check_torrent_filter(meta, {"type": MediaType.MOVIE})
        assert match

    def test_audio_only_flac_is_rejected(self):
        meta = _meta("[FLAC] Some Artist - Some Album")
        match, _, msg = IndexerFilterEngine.check_torrent_filter(meta, {"type": MediaType.MOVIE})
        assert not match
        assert "音频文件" in msg

    def test_audio_extension_is_rejected(self):
        meta = _meta("Some Artist - Some Album.flac")
        match, _, _ = IndexerFilterEngine.check_torrent_filter(meta, {"type": MediaType.MOVIE})
        assert not match


def test_rule_group_matches_chinese_subtitle_description():
    from types import SimpleNamespace

    meta = SimpleNamespace(
        rev_string="A Record of a Mortal's Journey to Immortality S01",
        subtitle=None,
        description="凡人修仙传 全30集 国语中字",
        size=None,
        upload_volume_factor=None,
        download_volume_factor=None,
        type=None,
        total_episodes=0,
    )
    match, _, _ = IndexerFilterEngine.check_rules(
        meta,
        {"name": "中字"},
        [{"include": ["中字"], "exclude": None, "size": None, "free": None, "pri": 0}],
    )
    assert match


def test_quick_name_match_uses_description_aliases():
    meta = SimpleNamespace(
        title="A Record of a Mortal's Journey to Immortality",
        cn_name="",
        en_name="",
        description="凡人修仙传 全30集 国语中字",
        type=None,
        rev_string="",
        org_string="",
        year="2020",
        size=0,
    )
    match = SimpleNamespace(
        title="凡人修仙传",
        cn_name="凡人修仙传",
        en_name="",
        original_title="",
        type=None,
        content_profile="",
        year="2020",
    )
    assert ResultFilter.quick_name_match(meta, match)

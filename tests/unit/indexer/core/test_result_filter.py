"""ResultFilter 测试：match_filter 缓存隔离 + local_filter 召回门语义"""

from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock, patch

import pytest

from app.db.repositories.config_repo_adapter import FilterGroupRepositoryAdapter, FilterRuleRepositoryAdapter
from app.domain.mediatypes import MediaType
from app.indexer.core.pipeline import SearchPipeline
from app.indexer.core.result_filter import ResultFilter
from app.media import meta_info as parse_title
from app.media.models import MediaInfo


def _no_rule_repos():
    """无规则组的仓库桩：filter_args 不含 rule 时直接通过规则检查"""

    class _GroupRepo:
        def get_all(self):
            return []

        def get_by_id(self, _id):
            return None

    class _RuleRepo:
        def get_by_group(self, _id):
            return []

    return (
        cast(FilterGroupRepositoryAdapter, _GroupRepo()),
        cast(FilterRuleRepositoryAdapter, _RuleRepo()),
    )


class _MediaStub:
    """MediaService 桩：merge_media_info 直接回填 tmdb_id"""

    def merge_media_info(self, target, source):
        target.tmdb_id = source.tmdb_id or target.tmdb_id
        return target


def _make_filter():
    group_repo, rule_repo = _no_rule_repos()
    return ResultFilter(media=_MediaStub(), filter_group_repo=group_repo, filter_rule_repo=rule_repo)


def _item(title, imdbid=None, description=""):
    return {
        "title": title,
        "description": description,
        "enclosure": "magnet:?xt=urn:btih:x",
        "size": 8 * 1024 * 1024 * 1024,
        "seeders": 10,
        "peers": 5,
        "page_url": "http://example.com/t",
        "uploadvolumefactor": 1.0,
        "downloadvolumefactor": 1.0,
        "imdbid": imdbid,
        "labels": "",
        "_indexer_name": "TestSite",
        "_indexer_order": 0,
        "_indexer_public": False,
    }


def _gits_2026():
    """攻壳机动队 (2026) 目标媒体"""
    return MediaInfo(
        cn_name="攻壳机动队",
        title="攻壳机动队",
        en_name="THE GHOST IN THE SHELL",
        year="2026",
        type=MediaType.ANIME,
        tmdb_id=255358,
    )


class TestLocalFilterQnmRecallGate:
    """ADR-014：quick_name_match 降级为纯召回筛选后的 local_filter 调用处语义"""

    def test_qnm_hit_with_en_name_no_longer_skips_tmdb(self):
        """qnm 命中且带 en_name（旧高置信直通路径）→ 现一律 skip_tmdb=False 交身份层"""
        rf = _make_filter()
        candidates, direct_results, stats = rf.local_filter(
            [_item("THE.GHOST.IN.THE.SHELL.S01E03.2026.1080p.AMZN.WEB-DL.H264.DDP-CMCTV")],
            filter_args={},
            match_media=_gits_2026(),
        )
        assert len(candidates) == 1
        assert candidates[0].skip_tmdb is False
        assert candidates[0].media_info is candidates[0].meta_info
        assert direct_results == []
        assert stats.index_sucess == 0

    def test_qnm_hit_cn_only_low_confidence_goes_to_tmdb(self):
        """qnm 命中但仅 cn_name（低置信）→ skip_tmdb=False 走 TMDB"""
        rf = _make_filter()
        candidates, direct_results, stats = rf.local_filter(
            [_item("[LoliHouse] 攻壳机动队 - 03 [WebRip 1080p]")],
            filter_args={},
            match_media=_gits_2026(),
        )
        assert len(candidates) == 1
        assert candidates[0].skip_tmdb is False
        assert direct_results == []

    def test_zero_intersection_rejected_and_records_miss(self):
        """名称与目标零交集 → 本地拒绝并记 miss（750 条泛词场景的召回门）"""
        rf = _make_filter()
        with patch("app.indexer.core.result_filter.get_miss_collector") as getter:
            collector = MagicMock()
            getter.return_value = collector
            candidates, direct_results, stats = rf.local_filter(
                [_item("Spy x Family S01 1080p")],
                filter_args={},
                match_media=_gits_2026(),
            )
        assert candidates == []
        assert direct_results == []
        assert stats.index_match_fail == 1
        collector.record.assert_called_once()
        assert collector.record.call_args[0][2] == "quick_name_miss"

    @patch("app.indexer.core.result_filter.cached_meta_info")
    def test_year_guard_with_zero_overlap_still_rejects(self, mock_parse):
        """年份守卫保留：种子年份与目标偏差>1 年且名称零交集 → 仍拒绝"""
        mi = parse_title(title="Frozen Planet II 2016 1080p")
        mi.cn_name = None
        mi.en_name = "FROZEN PLANET II"
        mi.year = "2016"
        mi.type = MediaType.TV
        mock_parse.return_value = mi
        match = _gits_2026()
        assert ResultFilter.quick_name_match(mi, match) is False
        rf = _make_filter()
        candidates, _, stats = rf.local_filter(
            [_item("Frozen Planet II 2016 1080p")], filter_args={}, match_media=match
        )
        assert candidates == []
        assert stats.index_match_fail == 1

    @patch("app.indexer.core.result_filter.cached_meta_info")
    def test_year_conflict_with_name_overlap_goes_to_tmdb(self, mock_parse):
        """年份冲突但名称有交集 → 不再本地拒绝，交身份层消歧（召回语义）"""
        mi = parse_title(title="Ghostbusters 2016 1080p")
        mi.cn_name = None
        mi.en_name = "Ghostbusters"
        mi.year = "2016"
        mi.type = MediaType.MOVIE
        mock_parse.return_value = mi
        match = MediaInfo(
            cn_name="捉鬼敢死队", title="捉鬼敢死队", en_name="Ghostbusters", year="1984", type=MediaType.MOVIE
        )
        assert ResultFilter.quick_name_match(mi, match) is False
        rf = _make_filter()
        candidates, _, stats = rf.local_filter([_item("Ghostbusters 2016 1080p")], filter_args={}, match_media=match)
        assert len(candidates) == 1
        assert candidates[0].skip_tmdb is False
        assert stats.index_match_fail == 0

    @patch("app.indexer.core.result_filter.cached_meta_info")
    def test_type_guard_with_zero_overlap_still_rejects(self, mock_parse):
        """类型守卫保留：电影≠剧集（互斥）且名称零交集 → 仍拒绝"""
        mi = parse_title(title="The Mandalorian S03 1080p")
        mi.cn_name = None
        mi.en_name = "The Mandalorian"
        mi.year = None
        mi.type = MediaType.TV
        mock_parse.return_value = mi
        match = MediaInfo(
            cn_name="泰坦尼克号", title="泰坦尼克号", en_name="Titanic", year="1997", type=MediaType.MOVIE
        )
        assert ResultFilter.quick_name_match(mi, match) is False
        rf = _make_filter()
        candidates, _, stats = rf.local_filter([_item("The Mandalorian S03 1080p")], filter_args={}, match_media=match)
        assert candidates == []
        assert stats.index_match_fail == 1

    def test_imdb_id_passthrough_preserved(self):
        """imdb_id 判等驱动的 skip_tmdb=True（ID 直通，合法证据）必须保留"""
        rf = _make_filter()
        match = _gits_2026()
        match.imdb_id = "tt1234567"
        candidates, _, _ = rf.local_filter(
            [_item("THE.GHOST.IN.THE.SHELL.S01E03.2026.1080p.AMZN.WEB-DL.H264.DDP-CMCTV", imdbid="tt1234567")],
            filter_args={},
            match_media=match,
        )
        assert len(candidates) == 1
        assert candidates[0].skip_tmdb is True

    def test_no_match_media_goes_to_direct_results(self):
        """无 match_media 分支不变：直接产出 direct_results，不查 TMDB"""
        rf = _make_filter()
        candidates, direct_results, stats = rf.local_filter(
            [_item("THE.GHOST.IN.THE.SHELL.S01E03.2026.1080p.AMZN.WEB-DL.H264.DDP-CMCTV")],
            filter_args={},
            match_media=None,
            search_name="THE GHOST IN THE SHELL",
        )
        assert candidates == []
        assert len(direct_results) == 1
        assert stats.index_sucess == 1


class TestCachedMediaInfoIsolation:
    """同组候选共享缓存对象：读取方必须深拷贝，否则
    1) `media_info not in ret_array` 判重塌缩（每组只剩一条）
    2) 后处理候选的 torrent_info 覆盖先前候选（张冠李戴）
    """

    def test_model_copy_isolates_torrent_info(self):
        cached = MediaInfo(cn_name="穹庐下的魔女", tmdb_id=288971, provider_data={"id": 288971})

        first = cached.model_copy(deep=True)
        first.set_torrent_info(site="SiteA", enclosure="magnet:a")
        second = cached.model_copy(deep=True)
        second.set_torrent_info(site="SiteB", enclosure="magnet:b")

        # 缓存对象不被污染
        assert cached.site is None or cached.site == ""
        # 两个候选互不影响
        assert first.enclosure == "magnet:a"
        assert second.enclosure == "magnet:b"
        # 判重按内容：org_string 不同的两条都应能入列
        first.org_string = "title A"
        second.org_string = "title B"
        ret_array = [first]
        assert second not in ret_array


@pytest.mark.parametrize(
    "title",
    [
        "凡人修仙传 S01E01 2020 1080p WEB-DL H264",
        "A Record of a Mortal's Journey to Immortality S01E01 2020 1080p WEB-DL H264",
    ],
)
def test_multilingual_torrent_survives_rule_and_identity_pipeline(title):
    group = SimpleNamespace(
        id=1,
        default=True,
        to_dict=lambda: {"id": 1, "name": "中字"},
    )
    rule = SimpleNamespace(include="中字", exclude="", note=None, priority=0)
    group_repo = MagicMock()
    group_repo.get_all.return_value = [group]
    group_repo.get_by_id.return_value = group
    rule_repo = MagicMock()
    rule_repo.get_by_group.return_value = [rule]
    media_service = MagicMock()
    media_service.get_all_names.return_value = []
    media_service.merge_media_info.side_effect = lambda target, source: target
    result_filter = ResultFilter(
        media=media_service,
        filter_group_repo=group_repo,
        filter_rule_repo=rule_repo,
    )
    pipeline = SearchPipeline(
        media_service=media_service,
        result_filter=result_filter,
        progress=MagicMock(),
    )
    match_media = MediaInfo(
        title="凡人修仙传",
        cn_name="凡人修仙传",
        en_name="A Record of a Mortal's Journey to Immortality",
        original_title="A Record of a Mortal's Journey to Immortality",
        year="2020",
        type=MediaType.TV,
        tmdb_id=106449,
        provider_data={"id": 106449, "name": "凡人修仙传", "media_type": "tv"},
    )

    result = pipeline.process(
        all_results=[_item(title, description="凡人修仙传 国语中字")],
        filter_args={"rule": 1, "year": "2020", "type": MediaType.TV.value},
        match_media=match_media,
        search_name="凡人修仙传",
    )

    assert len(result.results) == 1
    assert result.results[0].tmdb_id == 106449
    assert result.results[0].provider_data["name"] == "凡人修仙传"


class TestTitleSpecificityWithoutYear:
    def _match(self, **kwargs):
        from types import SimpleNamespace

        base = {
            "title": "生化危机：爆发夜",
            "cn_name": "生化危机：爆发夜",
            "en_name": "Resident Evil",
            "original_title": "Resident Evil",
        }
        base.update(kwargs)
        return SimpleNamespace(**base)

    def test_rejects_franchise_prefix_with_sequel_number(self):
        from app.indexer.core.result_filter import ResultFilter

        assert not ResultFilter._title_specific_without_year("RESIDENT EVIL 2 -CODEX", self._match())

    def test_accepts_specific_subtitle_without_year(self):
        from app.indexer.core.result_filter import ResultFilter

        match = self._match(original_title="Resident Evil The Umbrella Chronicles")
        assert ResultFilter._title_specific_without_year("Resident.Evil.The.Umbrella.Chronicles.2160p.WEB-DL", match)

    def test_accepts_chinese_title_without_year(self):
        from app.indexer.core.result_filter import ResultFilter

        assert ResultFilter._title_specific_without_year("生化危机：爆发夜 2160p", self._match())


def test_quick_name_match_ignores_zero_year():
    from types import SimpleNamespace

    from app.indexer.core.result_filter import ResultFilter

    meta = SimpleNamespace(
        title="Resident Evil 2026",
        cn_name="生化危机",
        en_name="Resident Evil",
        description="",
        year="2026",
        type=MediaType.MOVIE,
        rev_string="",
        org_string="",
    )
    match = SimpleNamespace(
        title="生化危机：爆发夜",
        cn_name="生化危机：爆发夜",
        en_name="Resident Evil",
        original_title="Resident Evil",
        year="0",
        type=MediaType.MOVIE,
    )
    assert ResultFilter.quick_name_match(meta, match)


class TestTitleSpecificityRejectsDifferentWorks:
    def _match(self, original="Resident Evil"):
        from types import SimpleNamespace

        return SimpleNamespace(
            title="生化危机：爆发夜",
            cn_name="生化危机：爆发夜",
            en_name="Resident Evil",
            original_title=original,
        )

    def _check(self, name, original="Resident Evil"):
        from app.indexer.core.result_filter import ResultFilter

        return ResultFilter._title_specific_without_year(name, self._match(original))

    def test_rejects_game_requiem(self):
        assert not self._check("PC ACT Resident Evil Requiem-voices38")

    def test_rejects_trilogy_collection(self):
        assert not self._check("Resident Evil trilogy Blu-ray 1080p HDbits@CHDBits")

    def test_accepts_full_specific_title(self):
        assert self._check(
            "Resident Evil Death Island 1080p BluRay DTS 5.1-CMCT",
            original="Resident Evil Death Island",
        )

    def test_rejects_sequel_number(self):
        assert not self._check("RESIDENT EVIL 2 -CODEX")
